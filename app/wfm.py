"""Planificación diaria versionada. Intervalos semiabiertos de 30 minutos.

Las revisiones son append-only. Cada publicación actualiza además una proyección
normalizada para las vistas de horarios, sin modificar registros históricos.
"""
import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import unicodedata
from uuid import uuid4

from .wfm_advanced import (
    EXCEPTION_TYPES,
    HORIZON_SLOTS,
    MAX_EXCEPTIONS,
    MAX_SEGMENTS,
    canonical_segments,
    default_break,
    exception_at,
    normalize_plan,
    operational_at,
    operational_slots,
    overlaps,
    segment_containing,
    shift_segments,
    working_slots,
)

TEAMS = ('Telefonista', 'Planificador', 'Supervisor')
# Cada plan pertenece al día en que empieza el turno. El horizonte se extiende
# hasta el mediodía siguiente para representar cruces de medianoche sin partir
# artificialmente la asignación.
TEAM_WINDOWS = {
    'Telefonista': (11, 60),  # 05:30 a 06:00 del día siguiente.
    'Planificador': (0, HORIZON_SLOTS),
    'Supervisor': (0, HORIZON_SLOTS),
}
TEAM_DEMAND_WINDOWS = {
    'Telefonista': (11, 44),
    'Planificador': (0, 48),
    'Supervisor': (0, 48),
}
# Base inicial editable desde la pantalla. Solo se usa al crear planes nuevos;
# un plan que ya tiene revisión conserva su propia curva de demanda.
DEFAULT_REQUIREMENTS = {
    'Telefonista': [3, 3, 3, 3, 3, 3, 3],
    'Planificador': [0, 0, 0, 0, 0, 0, 0],
    'Supervisor': [0, 0, 0, 0, 0, 0, 0],
}
WFM_DEFAULT_SETTINGS = {
    'shift_slots': 13,  # 6 h 30 min, en intervalos de 30 minutos.
    'break_slots': 1,   # 30 minutos.
}
SCHEMA = """CREATE TABLE IF NOT EXISTS wfm_revisions (
 plan_date TEXT NOT NULL, team TEXT NOT NULL, revision INTEGER NOT NULL,
 published INTEGER NOT NULL, payload TEXT NOT NULL, actor_id BIGINT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(plan_date,team,revision));
CREATE INDEX IF NOT EXISTS wfm_published_date ON wfm_revisions(published,plan_date);
CREATE TABLE IF NOT EXISTS wfm_published_plans (
 plan_date TEXT NOT NULL, team TEXT NOT NULL, revision INTEGER NOT NULL,
 actor_id BIGINT NOT NULL, published_at TEXT NOT NULL,
 PRIMARY KEY(plan_date,team));
CREATE TABLE IF NOT EXISTS wfm_published_shifts (
 plan_date TEXT NOT NULL, team TEXT NOT NULL, user_id BIGINT NOT NULL,
 revision INTEGER NOT NULL, start_slot INTEGER NOT NULL, end_slot INTEGER NOT NULL,
 segments TEXT NOT NULL, break_slot INTEGER, break_duration INTEGER NOT NULL,
 overtime_slots INTEGER NOT NULL, exceptions TEXT NOT NULL,
 actor_id BIGINT NOT NULL, published_at TEXT NOT NULL,
 PRIMARY KEY(plan_date,team,user_id));
CREATE INDEX IF NOT EXISTS wfm_published_shifts_date ON wfm_published_shifts(plan_date,team,user_id);
CREATE TABLE IF NOT EXISTS wfm_weekly_requirements (
 team TEXT NOT NULL, weekday INTEGER NOT NULL, required INTEGER NOT NULL,
 actor_id BIGINT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(team,weekday));
CREATE TABLE IF NOT EXISTS wfm_settings (
 setting_key TEXT PRIMARY KEY, value INTEGER NOT NULL,
 actor_id BIGINT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wfm_requests (
 request_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, team TEXT NOT NULL,
 request_type TEXT NOT NULL, requested_date TEXT NOT NULL,
 requested_start INTEGER, requested_end INTEGER, reason TEXT NOT NULL,
 status TEXT NOT NULL, resolution_note TEXT, reviewed_by BIGINT,
 applied_revision INTEGER, created_at TEXT NOT NULL, reviewed_at TEXT,
 source_revision INTEGER, source_shift TEXT, requester_name TEXT,
 cancelled_at TEXT, cancelled_by BIGINT);
CREATE INDEX IF NOT EXISTS wfm_requests_status ON wfm_requests(status,team,requested_date);
"""

WFM_REQUEST_COLUMNS = {
    'source_revision': 'INTEGER',
    'source_shift': 'TEXT',
    'requester_name': 'TEXT',
    'cancelled_at': 'TEXT',
    'cancelled_by': 'BIGINT',
}


def ensure_schema(database, postgres=False):
    """Completa aditivamente el esquema WFM de instalaciones existentes."""
    if postgres:
        for column, definition in WFM_REQUEST_COLUMNS.items():
            database.execute(f'ALTER TABLE wfm_requests ADD COLUMN IF NOT EXISTS {column} {definition}')
        return
    existing = {row[1] for row in database.execute('PRAGMA table_info(wfm_requests)').fetchall()}
    for column, definition in WFM_REQUEST_COLUMNS.items():
        if column not in existing:
            database.execute(f'ALTER TABLE wfm_requests ADD COLUMN {column} {definition}')


class WfmError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def manager(actor):
    # Conserva la regla general de acceso completo del Administrador.
    return actor.get('role_name') in ('Supervisor', 'Administrador')


def administrator(actor):
    return actor.get('role_name') == 'Administrador'


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise WfmError(f'{name}: debe ser entero entre {low} y {high}')
    return value


def day(value):
    try:
        result = date.fromisoformat(value).isoformat()
        if result != value:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise WfmError('Fecha inválida (AAAA-MM-DD)') from None


def coverage(plan, team=None):
    active_window = TEAM_WINDOWS.get(team) if team else None
    result = []
    for slot, required in enumerate(plan['demand']):
        operational = sum(operational_at(shift, slot) for shift in plan['shifts'])
        if active_window and not active_window[0] <= slot < active_window[1]:
            result.append({'required': required, 'operational': operational, 'difference': 0})
            continue
        result.append({'required': required, 'operational': operational,
                       'difference': None if required is None else operational - required})
    return result


def warnings(plan, team=None):
    result = []
    for shift in plan['shifts']:
        break_duration = shift.get('break_duration', 1)
        if not break_duration or shift.get('break') is None:
            continue
        segment = segment_containing(shift, shift['break'], break_duration)
        if segment and (shift['break'] < segment['start'] + 4 or shift['break'] + break_duration > segment['end'] - 4):
            result.append(f"Agente {shift['user_id']}: descanso fuera del margen habitual de dos horas")
    deficits = sum(r['difference'] is not None and r['difference'] < 0 for r in coverage(plan, team))
    if deficits:
        result.append(f'{deficits} franjas con cobertura insuficiente')
    active_window = TEAM_WINDOWS.get(team)
    demand = plan['demand'] if not active_window else plan['demand'][active_window[0]:active_window[1]]
    if any(v is None for v in demand):
        result.append('Hay franjas sin demanda informada; no equivalen a cero')
    return result


def validate(data, people, team=None, settings=None):
    if not isinstance(data, dict):
        raise WfmError('Plan inválido')
    demand = data.get('demand')
    if not isinstance(demand, list) or len(demand) not in (48, HORIZON_SLOTS):
        raise WfmError(f'Complete las {HORIZON_SLOTS} franjas del horizonte operativo')
    if len(demand) == 48:
        demand = demand + [0] * (HORIZON_SLOTS - 48)
    demand = [None if v is None else integer(v, 0, 10000, 'Demanda') for v in demand]
    source = data.get('shifts')
    if not isinstance(source, list) or len(source) > 500:
        raise WfmError('Lista de turnos inválida (máximo 500)')
    settings = settings or WFM_DEFAULT_SETTINGS
    shift_slots = settings['shift_slots']
    break_slots = settings['break_slots']
    shifts, seen = [], set()
    active_window = TEAM_WINDOWS.get(team)
    for s in source:
        if not isinstance(s, dict):
            raise WfmError('Turno inválido')
        uid = integer(s.get('user_id'), 1, 2**53-1, 'Agente')
        if uid not in people or uid in seen:
            raise WfmError('Agente duplicado, inactivo o ajeno al equipo')
        seen.add(uid)
        raw_segments = s.get('segments')
        if raw_segments is None:
            start = integer(s.get('start'), 0, 47, 'Inicio')
            raw_end = s.get('end', start + shift_slots)
            if type(raw_end) is int and raw_end <= start and raw_end <= 48:
                raw_end += 48
            end = integer(raw_end, start + 1, HORIZON_SLOTS, 'Fin')
            raw_segments = [dict(start=start, end=end)]
        if not isinstance(raw_segments, list) or not 1 <= len(raw_segments) <= MAX_SEGMENTS:
            raise WfmError(f'Cada agente debe tener entre 1 y {MAX_SEGMENTS} bloques de turno')
        segments = []
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                raise WfmError('Bloque de turno inválido')
            segment_start = integer(raw_segment.get('start'), 0, HORIZON_SLOTS - 1, 'Inicio de bloque')
            segment_end = integer(raw_segment.get('end'), segment_start + 1, HORIZON_SLOTS, 'Fin de bloque')
            segments.append(dict(start=segment_start, end=segment_end))
        segments.sort(key=lambda item: (item['start'], item['end']))
        if segments[0]['start'] >= 48:
            raise WfmError('El turno debe comenzar en el día seleccionado')
        if any(current['start'] < previous['end'] for previous, current in zip(segments, segments[1:])):
            raise WfmError('Los bloques de un turno no pueden superponerse')
        segments = canonical_segments(segments)
        start, end = segments[0]['start'], segments[-1]['end']
        break_duration = integer(s.get('break_duration', break_slots), 0, 4, 'Duración del descanso')
        if active_window and (start < active_window[0] or end > active_window[1]):
            label = 'Telefonistas' if team == 'Telefonista' else team
            raise WfmError(f'El turno de {label} queda fuera de su horizonte operativo')
        if working_slots(dict(segments=segments)) < break_duration + 2:
            raise WfmError('El turno debe incluir tiempo operativo y descanso')
        pause = s.get('break')
        if pause is None and break_duration:
            pause = default_break(segments, break_duration)
        if break_duration:
            pause = integer(pause, 0, HORIZON_SLOTS - 1, 'Descanso')
            if not segment_containing(dict(segments=segments), pause, break_duration):
                raise WfmError('El descanso debe quedar dentro de un bloque de trabajo')
        elif pause is not None:
            raise WfmError('Un turno sin descanso no debe indicar horario de descanso')
        overtime_slots = integer(s.get('overtime_slots', 0), 0, 24, 'Horas extras')
        if overtime_slots > working_slots(dict(segments=segments)):
            raise WfmError('Las horas extras no pueden superar la duración del turno')
        raw_exceptions = s.get('exceptions', [])
        if not isinstance(raw_exceptions, list) or len(raw_exceptions) > MAX_EXCEPTIONS:
            raise WfmError(f'Lista de excepciones inválida (máximo {MAX_EXCEPTIONS})')
        exceptions = []
        exception_ids = set()
        for index, exception in enumerate(raw_exceptions):
            if not isinstance(exception, dict) or exception.get('type') not in EXCEPTION_TYPES:
                raise WfmError('Tipo de excepción inválido')
            exception_start = integer(exception.get('start'), 0, HORIZON_SLOTS - 1, 'Inicio de excepción')
            exception_end = integer(exception.get('end'), exception_start + 1, HORIZON_SLOTS, 'Fin de excepción')
            if not any(segment['start'] <= exception_start and exception_end <= segment['end'] for segment in segments):
                raise WfmError('La excepción debe quedar completamente contenida en un bloque de trabajo')
            if any(overlaps(item['start'], item['end'], exception_start, exception_end) for item in exceptions):
                raise WfmError('Las excepciones de un turno no pueden superponerse')
            note = str(exception.get('note') or '').strip()
            if len(note) > 240:
                raise WfmError('La nota de la excepción admite hasta 240 caracteres')
            exception_id = str(exception.get('id') or f'exc-{index + 1}').strip()
            if not exception_id or len(exception_id) > 64:
                raise WfmError('Identificador de excepción inválido')
            if exception_id in exception_ids:
                raise WfmError('Las excepciones de un turno deben tener identificadores únicos')
            exception_ids.add(exception_id)
            clean = dict(id=exception_id, type=exception['type'], start=exception_start, end=exception_end, note=note)
            if exception.get('source_request_id'):
                clean['source_request_id'] = str(exception['source_request_id'])[:64]
            exceptions.append(clean)
        locked = s.get('locked', False)
        if type(locked) is not bool:
            raise WfmError('Bloqueo de descanso inválido')
        shifts.append(dict(
            user_id=uid,
            start=start,
            end=end,
            segments=segments,
            **{'break': pause, 'break_duration': break_duration},
            overtime_slots=overtime_slots,
            exceptions=exceptions,
            locked=locked,
        ))
    return dict(demand=demand, shifts=shifts)


def _store_published_plan(query, plan_date, team, revision, plan, actor_id, timestamp):
    """Reemplaza la proyección vigente sin tocar el historial de revisiones."""
    query('DELETE FROM wfm_published_shifts WHERE plan_date=? AND team=?', (plan_date, team))
    query(
        'INSERT INTO wfm_published_plans(plan_date,team,revision,actor_id,published_at) '
        'VALUES(?,?,?,?,?) ON CONFLICT(plan_date,team) DO UPDATE SET '
        'revision=excluded.revision,actor_id=excluded.actor_id,published_at=excluded.published_at',
        (plan_date, team, revision, actor_id, timestamp),
    )
    for shift in plan.get('shifts', []):
        query(
            'INSERT INTO wfm_published_shifts('
            'plan_date,team,user_id,revision,start_slot,end_slot,segments,break_slot,'
            'break_duration,overtime_slots,exceptions,actor_id,published_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                plan_date, team, shift['user_id'], revision, shift['start'], shift['end'],
                json.dumps(shift_segments(shift)), shift.get('break'), shift.get('break_duration', 1),
                shift.get('overtime_slots', 0), json.dumps(shift.get('exceptions', [])),
                actor_id, timestamp,
            ),
        )


def _published_row(plan_date, team, revision, shift, person, timestamp):
    start, end = shift['start'], shift['end']
    plan_day = date.fromisoformat(plan_date)
    return dict(
        id=f'{plan_date}:{team}:{shift["user_id"]}', user_id=shift['user_id'],
        schedule_date=plan_date,
        week_start=(plan_day-timedelta(days=plan_day.weekday())).isoformat(),
        role_name=team, team=team, display_name=person.get('display_name', 'Usuario no disponible'),
        shift_name='Jornada partida' if len(shift_segments(shift)) > 1 else 'Turno publicado',
        start_time=f'{(start % 48)//2:02d}:{"30" if start % 2 else "00"}',
        end_time=f'{(end % 48)//2:02d}:{"30" if end % 2 else "00"}',
        start_slot=start, end_slot=end, crosses_midnight=end > 48,
        segments=shift_segments(shift), break_slot=shift.get('break'),
        break_duration=shift.get('break_duration', 1),
        overtime_slots=shift.get('overtime_slots', 0), exceptions=shift.get('exceptions', []),
        notes='', revision=revision, published_at=str(timestamp), source='wfm',
        created_by='', created_at=str(timestamp), updated_at=str(timestamp),
    )


def _slot_from_time(value):
    if value is None:
        return None
    text = value.isoformat() if hasattr(value, 'isoformat') else str(value)
    try:
        hours, minutes = text[:5].split(':')
        return int(hours) * 2 + int(minutes) // 30
    except (TypeError, ValueError):
        return None


def _published_schedules(query, params, postgres):
    raw_week = params.get('week')
    if raw_week:
        requested = date.fromisoformat(day(raw_week))
        first = requested-timedelta(days=requested.weekday())
        start, end = first.isoformat(), (first+timedelta(days=6)).isoformat()
    else:
        raw_start, raw_end = params.get('date_from'), params.get('date_to')
        start = day(raw_start) if raw_start else '1970-01-01'
        end = day(raw_end) if raw_end else '2100-12-31'
    span = (date.fromisoformat(end)-date.fromisoformat(start)).days
    if span < 0 or (not raw_week and raw_start and raw_end and span > 366):
        raise WfmError('El período publicado debe estar ordenado y abarcar hasta 367 días')
    team = str(params.get('team') or params.get('role') or '').strip()
    if team and team not in TEAMS:
        raise WfmError('Equipo inválido')
    try:
        employee_id = int(params['employee_id']) if params.get('employee_id') else None
    except (TypeError, ValueError):
        raise WfmError('Persona inválida') from None
    people = {row['id']: dict(row) for row in query(
        'SELECT u.id,u.display_name,u.active,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id'
    ).fetchall()}
    plans = query(
        'SELECT * FROM wfm_published_plans WHERE plan_date>=? AND plan_date<=? '
        'ORDER BY plan_date DESC,team',
        (start, end),
    ).fetchall()
    projected = {
        ((row['plan_date'].isoformat() if hasattr(row['plan_date'], 'isoformat') else str(row['plan_date'])), row['team']): int(row['revision'])
        for row in plans
    }
    stored = query(
        'SELECT * FROM wfm_published_shifts WHERE plan_date>=? AND plan_date<=? '
        'ORDER BY plan_date DESC,team,user_id',
        (start, end),
    ).fetchall()
    result = []
    for record in stored:
        item = dict(record)
        plan_date = item['plan_date'].isoformat() if hasattr(item['plan_date'], 'isoformat') else str(item['plan_date'])
        shift = dict(
            user_id=item['user_id'], start=item['start_slot'], end=item['end_slot'],
            segments=json.loads(item['segments']), break_duration=item['break_duration'],
            overtime_slots=item['overtime_slots'], exceptions=json.loads(item['exceptions']),
            **{'break': item['break_slot']},
        )
        result.append(_published_row(plan_date, item['team'], item['revision'], shift, people.get(item['user_id'], {}), item['published_at']))
    revisions = query(
        'SELECT * FROM wfm_revisions WHERE published=1 AND plan_date>=? AND plan_date<=? '
        'ORDER BY plan_date DESC,team,revision DESC',
        (start, end),
    ).fetchall()
    seen = set()
    published_plan_keys = set(projected)
    for record in revisions:
        item = dict(record)
        plan_date = item['plan_date'].isoformat() if hasattr(item['plan_date'], 'isoformat') else str(item['plan_date'])
        key = (plan_date, item['team'])
        if key in seen:
            continue
        seen.add(key)
        published_plan_keys.add(key)
        if projected.get(key, 0) >= int(item['revision']):
            continue
        for shift in normalize_plan(json.loads(item['payload'])).get('shifts', []):
            result.append(_published_row(plan_date, item['team'], item['revision'], shift, people.get(shift['user_id'], {}), item['created_at']))
    legacy = query(
        'SELECT s.*,COALESCE(u.display_name,\'Usuario no disponible\') display_name,'
        'COALESCE(NULLIF(s.role_name,\'\'),r.name,\'\') effective_role '
        'FROM work_schedules s LEFT JOIN users u ON u.id=s.user_id '
        'LEFT JOIN roles r ON r.id=u.role_id WHERE s.schedule_date>=? AND s.schedule_date<=? '
        'ORDER BY s.schedule_date,s.start_time,s.id',
        (start, end),
    ).fetchall()
    for record in legacy:
        item = dict(record)
        plan_date = item['schedule_date'].isoformat() if hasattr(item['schedule_date'], 'isoformat') else str(item['schedule_date'])
        legacy_team = item.get('effective_role') or item.get('role_name') or ''
        if (plan_date, legacy_team) in published_plan_keys:
            continue
        start_slot, end_slot = _slot_from_time(item.get('start_time')), _slot_from_time(item.get('end_time'))
        if start_slot is not None and end_slot is not None and end_slot <= start_slot:
            end_slot += 48
        segments = [dict(start=start_slot, end=end_slot)] if start_slot is not None and end_slot is not None else []
        result.append(dict(
            id=f'legacy:{item["id"]}', user_id=item['user_id'], schedule_date=plan_date,
            week_start=(item['week_start'].isoformat() if hasattr(item['week_start'], 'isoformat') else str(item['week_start'])),
            role_name=legacy_team, team=legacy_team, display_name=item['display_name'],
            shift_name=item.get('shift_name') or 'Horario histórico',
            start_time=(str(item.get('start_time'))[:5] if item.get('start_time') is not None else None),
            end_time=(str(item.get('end_time'))[:5] if item.get('end_time') is not None else None),
            start_slot=start_slot, end_slot=end_slot,
            crosses_midnight=bool(end_slot is not None and end_slot > 48), segments=segments,
            break_slot=None, break_duration=0, overtime_slots=0, exceptions=[], revision=None,
            published_at=(item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])),
            source='legacy', notes=item.get('notes') or '', created_by=item.get('created_by') or '',
            created_at=(item['created_at'].isoformat() if hasattr(item['created_at'], 'isoformat') else str(item['created_at'])),
            updated_at=(item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])),
        ))
    query_text = str(params.get('q') or '').strip().casefold()
    filtered = []
    for row in result:
        if team and row['team'] != team:
            continue
        if employee_id is not None and row['user_id'] != employee_id:
            continue
        exception_text = ' '.join(f"{item.get('type','')} {item.get('note','')}" for item in row['exceptions'])
        time_text = f"{row.get('start_time') or ''} {row.get('end_time') or ''}"
        if query_text and query_text not in ' '.join((row['display_name'], row['team'], row['shift_name'], row.get('notes', ''), exception_text, time_text, row.get('source', ''))).casefold():
            continue
        filtered.append(row)
    return sorted(filtered, key=lambda row: (row['schedule_date'], row['start_slot'] if row['start_slot'] is not None else -1, row['display_name']))


def optimize(plan, team=None):
    """Mejora local determinista; no promete una solución óptima ni cero déficit."""
    plan = copy.deepcopy(plan)
    active_window = TEAM_WINDOWS.get(team)
    demand = plan['demand'] if not active_window else plan['demand'][active_window[0]:active_window[1]]
    if any(v is None for v in demand):
        raise WfmError('Informá toda la curva de demanda antes de distribuir descansos')

    counts = [r['operational'] for r in coverage(plan, team)]

    def candidate_range(shift):
        result = []
        duration = shift.get('break_duration', 1)
        for segment in shift_segments(shift):
            result.extend(range(segment['start'] + 4, segment['end'] - duration - 3))
        return result

    def pause_slots(shift, pause=None):
        start = shift['break'] if pause is None else pause
        return [
            slot for slot in range(start, start + shift.get('break_duration', 1))
            if exception_at(shift, slot) is None
        ]

    def score():
        diffs = [op-req for op,req in zip(counts,plan['demand'])]
        return (sum(max(0, -v)**2 for v in diffs),
                sum(abs(s['break'] - (s['start'] + s['end'] - 1)/2) for s in plan['shifts']))

    for _ in range(8):
        changed = False
        for s in plan['shifts']:
            if s['locked'] or not s.get('break_duration', 1) or s.get('break') is None:
                continue
            old, best, best_score = s['break'], s['break'], score()
            for slot in pause_slots(s):
                counts[slot] += 1
            for pause in candidate_range(s):
                s['break'] = pause
                for slot in pause_slots(s):
                    counts[slot] -= 1
                candidate = score()
                for slot in pause_slots(s):
                    counts[slot] += 1
                if candidate < best_score:
                    best, best_score = pause, candidate
            s['break'] = best
            for slot in pause_slots(s):
                counts[slot] -= 1
            changed |= best != old
        if not changed:
            break
    return plan


def default_requirements(team):
    return list(DEFAULT_REQUIREMENTS[team])


def default_wfm_settings():
    return dict(WFM_DEFAULT_SETTINGS)


def _settings_response(values):
    shift_slots = int(values['shift_slots'])
    break_slots = int(values['break_slots'])
    return dict(
        shift_slots=shift_slots,
        break_slots=break_slots,
        shift_minutes=shift_slots * 30,
        break_minutes=break_slots * 30,
    )


def load_wfm_settings(query, actor_id):
    defaults = default_wfm_settings()
    timestamp = datetime.now(timezone.utc).isoformat()
    for setting_key, value in defaults.items():
        query(
            'INSERT INTO wfm_settings(setting_key,value,actor_id,updated_at) '
            'VALUES(?,?,?,?) ON CONFLICT(setting_key) DO NOTHING',
            (setting_key, value, actor_id, timestamp),
        )
    records = query('SELECT setting_key,value FROM wfm_settings').fetchall()
    values = defaults.copy()
    for record in records:
        if record['setting_key'] in values:
            values[record['setting_key']] = int(record['value'])
    return _settings_response(values)


def validate_wfm_settings(data):
    if not isinstance(data, dict):
        raise WfmError('Configuración de WFM inválida')
    shift_minutes = data.get('shift_minutes')
    break_minutes = data.get('break_minutes')
    if shift_minutes is None and 'shift_slots' in data:
        shift_minutes = data['shift_slots'] * 30 if type(data['shift_slots']) is int else None
    if break_minutes is None and 'break_slots' in data:
        break_minutes = data['break_slots'] * 30 if type(data['break_slots']) is int else None
    if type(shift_minutes) is not int or shift_minutes < 30 or shift_minutes > 720 or shift_minutes % 30:
        raise WfmError('La duración del turno debe estar entre 30 y 720 minutos, en bloques de 30')
    if type(break_minutes) is not int or break_minutes < 30 or break_minutes > 120 or break_minutes % 30:
        raise WfmError('El descanso debe estar entre 30 y 120 minutos, en bloques de 30')
    return dict(shift_slots=shift_minutes // 30, break_slots=break_minutes // 30)


WEEKLY_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / 'data' / 'wfm' / 'telefonistas-horarios-2026-W37.json'


def _normalized_name(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(text.casefold().replace('.', ' ').split())


def weekly_template(team):
    if team != 'Telefonista':
        return {}
    try:
        source = json.loads(WEEKLY_TEMPLATE_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        # La ausencia de datos WFM debe comportarse como una plantilla vacía
        # para que los consumidores puedan aplicar sus validaciones normales.
        return {}
    if source.get('team') != team or not isinstance(source.get('people'), list):
        return {}
    return source


def _template_slot(value):
    try:
        hours, minutes = str(value).split(':')
        hours, minutes = int(hours), int(minutes)
        if minutes not in (0, 30) or hours < 0 or hours > 24 or (hours == 24 and minutes):
            raise ValueError()
        return hours * 2 + minutes // 30
    except (TypeError, ValueError):
        return None


def weekly_schedule_for_people(people, team, plan_date=None):
    """Resuelve la plantilla histórica contra los usuarios activos del equipo."""
    source = weekly_template(team)
    templates = source.get('people', [])
    selected_weekday = date.fromisoformat(plan_date).weekday() if plan_date else None
    in_effective_week = bool(
        plan_date and source.get('effective_week', {}).get('start') <= plan_date
        <= source.get('effective_week', {}).get('end')
    ) if source.get('effective_week') else False
    resolved = []
    for person in people:
        person_name = _normalized_name(person.get('display_name'))
        item = next(
            (
                candidate for candidate in templates
                if person_name in {
                    _normalized_name(candidate.get('name')),
                    _normalized_name(candidate.get('alias')),
                }
            ),
            None,
        )
        if not item:
            continue
        start, end = _template_slot(item.get('start')), _template_slot(item.get('end'))
        day_off = item.get('day_off')
        if start is None or end is None or not isinstance(day_off, int) or not 0 <= day_off <= 6:
            continue
        if start < 0 or end > 48 or end <= start:
            continue
        pause = start + max(1, (end - start - 1) // 2)
        schedule = dict(
            user_id=person['id'], display_name=person['display_name'],
            start=start, end=end, break_slot=pause, day_off=day_off,
        )
        if in_effective_week and isinstance(item.get('days'), dict):
            override = item['days'].get(str(selected_weekday))
            if isinstance(override, dict):
                status = str(override.get('status') or '').strip()
                if status:
                    schedule.update(day_off=selected_weekday, day_status=status, source_week=source['effective_week']['start'])
                else:
                    day_start, day_end = _template_slot(override.get('start')), _template_slot(override.get('end'))
                    day_break = _template_slot(override.get('break'))
                    overtime = _template_slot(override.get('overtime')) if override.get('overtime') else 0
                    if day_start is not None and day_end is not None and day_start < day_end <= 48:
                        if day_break is not None and not day_start <= day_break < day_end:
                            day_break = None
                        schedule.update(
                            start=day_start, end=day_end, break_slot=day_break,
                            break_duration=1 if day_break is not None else 0,
                            overtime_slots=overtime or 0, day_off=-1,
                            source_week=source['effective_week']['start'],
                        )
        resolved.append(schedule)
    return resolved


def default_shifts(weekly_schedule, plan_date, settings=None):
    weekday = date.fromisoformat(plan_date).weekday()
    return [
        dict(
            user_id=item['user_id'], start=item['start'], end=item['end'],
            segments=[dict(start=item['start'], end=item['end'])],
            **{
                'break': item.get('break_slot'),
                'break_duration': item.get('break_duration', (settings or WFM_DEFAULT_SETTINGS)['break_slots']),
            },
            overtime_slots=item.get('overtime_slots', 0), exceptions=[], locked=False,
        )
        for item in weekly_schedule if item['day_off'] != weekday
    ]


def load_requirements(query, team, actor_id):
    defaults = default_requirements(team)
    timestamp = datetime.now(timezone.utc).isoformat()
    for weekday, required in enumerate(defaults):
        query(
            'INSERT INTO wfm_weekly_requirements(team,weekday,required,actor_id,updated_at) '
            'VALUES(?,?,?,?,?) ON CONFLICT(team,weekday) DO NOTHING',
            (team, weekday, required, actor_id, timestamp),
        )
    records = query(
        'SELECT weekday,required FROM wfm_weekly_requirements WHERE team=? ORDER BY weekday',
        (team,),
    ).fetchall()
    values = [None] * 7
    for record in records:
        values[int(record['weekday'])] = int(record['required'])
    return [defaults[index] if value is None else value for index, value in enumerate(values)]


def validate_requirements(data):
    source = data.get('requirements') if isinstance(data, dict) else None
    if isinstance(source, dict):
        values = [source.get(str(index), source.get(index)) for index in range(7)]
    else:
        values = source
    if not isinstance(values, list) or len(values) != 7:
        raise WfmError('La configuración semanal debe tener siete días')
    return [integer(value, 0, 10000, 'Agentes requeridos') for value in values]


def daily_demand(requirements, plan_date, team):
    start, end = TEAM_DEMAND_WINDOWS[team]
    weekday = date.fromisoformat(plan_date).weekday()
    demand = [0] * HORIZON_SLOTS
    for slot in range(start, end):
        demand[slot] = requirements[(weekday + slot // 48) % 7]
    return demand


def fill_missing_demand(plan, requirements, plan_date, team):
    """Completa huecos legacy en la respuesta sin tocar la revisión almacenada."""
    source_demand = plan.get('demand') if isinstance(plan, dict) else None
    migrated = isinstance(source_demand, list) and len(source_demand) < HORIZON_SLOTS
    result = normalize_plan(plan)
    demand = result.get('demand')
    if not isinstance(demand, list) or len(demand) != HORIZON_SLOTS:
        return result, False
    weekday = date.fromisoformat(plan_date).weekday()
    demand_start, demand_end = TEAM_DEMAND_WINDOWS[team]
    filled = migrated
    for slot, value in enumerate(demand):
        if value is None:
            demand[slot] = requirements[(weekday + slot // 48) % 7] if demand_start <= slot < demand_end else 0
            filled = True
    return result, filled


def _serializable_record(record):
    result = dict(record)
    for key, value in list(result.items()):
        if hasattr(value, 'isoformat'):
            result[key] = value.isoformat()
    return result


def _request_rows(query, actor, params, postgres):
    sql = (
        'SELECT q.*,COALESCE(q.requester_name,u.display_name,\'Usuario no disponible\') display_name,'
        'reviewer.display_name reviewer_name FROM wfm_requests q '
        'LEFT JOIN users u ON u.id=q.user_id '
        'LEFT JOIN users reviewer ON reviewer.id=q.reviewed_by WHERE TRUE'
    )
    values = []
    own_scope = params.get('scope') == 'mine'
    if manager(actor) and not own_scope:
        status = params.get('status')
        team = params.get('team')
        if status:
            if status not in ('PENDIENTE', 'APROBADA', 'RECHAZADA', 'CANCELADA'):
                raise WfmError('Estado de solicitud inválido')
            sql += ' AND q.status=?'
            values.append(status)
        if team:
            if team not in TEAMS:
                raise WfmError('Equipo inválido')
            sql += ' AND q.team=?'
            values.append(team)
        request_type = params.get('request_type')
        if request_type:
            if request_type not in ('AUSENCIA', 'CAMBIO_TURNO'):
                raise WfmError('Tipo de solicitud inválido')
            sql += ' AND q.request_type=?'
            values.append(request_type)
        date_from, date_to = params.get('date_from'), params.get('date_to')
        if date_from and date_to and day(date_from) > day(date_to):
            raise WfmError('El período de solicitudes no está ordenado')
        if date_from:
            sql += ' AND q.requested_date>=?'
            values.append(day(date_from))
        if date_to:
            sql += ' AND q.requested_date<=?'
            values.append(day(date_to))
        search = str(params.get('q') or '').strip()
        if search:
            sql += (' AND lower(COALESCE(q.requester_name,u.display_name,\'\')||\' \'||q.reason||\' \'||'
                    'COALESCE(q.resolution_note,\'\')) LIKE lower(?)')
            values.append(f'%{search}%')
    else:
        sql += ' AND q.user_id=?'
        values.append(actor['id'])
    sql += ' ORDER BY CASE q.status WHEN \'PENDIENTE\' THEN 0 ELSE 1 END,q.created_at DESC'
    result = []
    for row in query(sql, tuple(values)).fetchall():
        item = _serializable_record(row)
        if item.get('source_shift'):
            try:
                item['source_shift'] = json.loads(item['source_shift'])
            except (TypeError, json.JSONDecodeError):
                item['source_shift'] = None
        if item.get('status') == 'APROBADA' and item.get('applied_revision') is not None:
            revision = query(
                'SELECT payload FROM wfm_revisions WHERE plan_date=? AND team=? AND revision=? LIMIT 1',
                (item['requested_date'], item['team'], item['applied_revision']),
            ).fetchone()
            if revision:
                plan = normalize_plan(json.loads(dict(revision)['payload']))
                item['applied_shift'] = next(
                    (dict(shift) for shift in plan.get('shifts', []) if shift.get('user_id') == item['user_id']),
                    None,
                )
        result.append(item)
    return result


def _request_interval(data, required):
    raw_start, raw_end = data.get('requested_start'), data.get('requested_end')
    if raw_start is None and raw_end is None and not required:
        return None, None
    start = integer(raw_start, 0, 47, 'Inicio solicitado')
    end = integer(raw_end, start + 1, HORIZON_SLOTS, 'Fin solicitado')
    return start, end


def _create_request(query, actor, data, postgres):
    if actor.get('role_name') not in TEAMS:
        raise WfmError('El rol no pertenece a un equipo planificable', 403)
    if not isinstance(data, dict):
        raise WfmError('Solicitud inválida')
    request_type = data.get('request_type')
    if request_type not in ('AUSENCIA', 'CAMBIO_TURNO'):
        raise WfmError('Tipo de solicitud inválido')
    requested_date = day(data.get('requested_date'))
    reason = str(data.get('reason') or '').strip()
    if not 3 <= len(reason) <= 500:
        raise WfmError('El motivo debe tener entre 3 y 500 caracteres')
    start, end = _request_interval(data, request_type == 'CAMBIO_TURNO')
    if postgres:
        query('SELECT pg_advisory_xact_lock(73139030)')
        query('SELECT pg_advisory_xact_lock(73139031)')
    else:
        query('BEGIN IMMEDIATE')
    published = query(
        'SELECT * FROM wfm_revisions WHERE plan_date=? AND team=? AND published=1 '
        'ORDER BY revision DESC LIMIT 1',
        (requested_date, actor['role_name']),
    ).fetchone()
    if not published:
        raise WfmError('No hay un horario publicado para esa fecha', 409)
    published = dict(published)
    source_plan = normalize_plan(json.loads(published['payload']))
    source_shift = next(
        (dict(item) for item in source_plan.get('shifts', []) if item.get('user_id') == actor['id']),
        None,
    )
    if not source_shift:
        raise WfmError('No tenés un turno publicado en esa fecha', 409)
    if request_type == 'AUSENCIA' and start is not None:
        if not any(segment['start'] <= start and end <= segment['end'] for segment in shift_segments(source_shift)):
            raise WfmError('La ausencia parcial debe quedar dentro de un bloque del turno publicado')
    duplicate = query(
        'SELECT request_id FROM wfm_requests WHERE user_id=? AND requested_date=? AND status=\'PENDIENTE\' LIMIT 1',
        (actor['id'], requested_date),
    ).fetchone()
    if duplicate:
        raise WfmError('Ya tenés una solicitud pendiente para esa fecha', 409)
    request_id = uuid4().hex
    timestamp = datetime.now(timezone.utc).isoformat()
    query(
        'INSERT INTO wfm_requests(request_id,user_id,team,request_type,requested_date,'
        'requested_start,requested_end,reason,status,created_at,source_revision,source_shift,requester_name) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (request_id, actor['id'], actor['role_name'], request_type, requested_date,
         start, end, reason, 'PENDIENTE', timestamp, int(published['revision']),
         json.dumps(source_shift), actor.get('display_name') or 'Usuario'),
    )
    return dict(
        request_id=request_id, user_id=actor['id'], team=actor['role_name'],
        request_type=request_type, requested_date=requested_date,
        requested_start=start, requested_end=end, reason=reason,
        status='PENDIENTE', created_at=timestamp, source_revision=int(published['revision']),
        source_shift=source_shift, display_name=actor.get('display_name') or 'Usuario',
    )


def _cancel_request(query, actor, data, postgres):
    request_id = str(data.get('request_id') or '').strip() if isinstance(data, dict) else ''
    if not request_id:
        raise WfmError('Solicitud inválida')
    if postgres:
        query('SELECT pg_advisory_xact_lock(73139031)')
    else:
        query('BEGIN IMMEDIATE')
    suffix = ' FOR UPDATE' if postgres else ''
    request = query('SELECT * FROM wfm_requests WHERE request_id=?' + suffix, (request_id,)).fetchone()
    if not request:
        raise WfmError('Solicitud inexistente', 404)
    request = _serializable_record(request)
    if request['user_id'] != actor['id']:
        raise WfmError('Solo podés cancelar una solicitud propia', 403)
    if request['status'] != 'PENDIENTE':
        raise WfmError('Solo se pueden cancelar solicitudes pendientes', 409)
    timestamp = datetime.now(timezone.utc).isoformat()
    query(
        'UPDATE wfm_requests SET status=\'CANCELADA\',cancelled_at=?,cancelled_by=? WHERE request_id=?',
        (timestamp, actor['id'], request_id),
    )
    request.update(status='CANCELADA', cancelled_at=timestamp, cancelled_by=actor['id'])
    return request


def _decide_request(query, actor, data, postgres):
    if not manager(actor):
        raise WfmError('La bandeja de solicitudes es exclusiva de Supervisión', 403)
    if not isinstance(data, dict):
        raise WfmError('Decisión inválida')
    request_id = str(data.get('request_id') or '').strip()
    decision = data.get('decision')
    note = str(data.get('resolution_note') or '').strip()
    if not request_id or decision not in ('APROBAR', 'RECHAZAR') or len(note) > 500:
        raise WfmError('Decisión de solicitud inválida')
    if postgres:
        query('SELECT pg_advisory_xact_lock(73139030)')
    else:
        query('BEGIN IMMEDIATE')
    suffix = ' FOR UPDATE' if postgres else ''
    request = query(
        'SELECT q.*,u.display_name,r.name role_name FROM wfm_requests q '
        'JOIN users u ON u.id=q.user_id JOIN roles r ON r.id=u.role_id '
        'WHERE q.request_id=?' + suffix,
        (request_id,),
    ).fetchone()
    if not request:
        raise WfmError('Solicitud inexistente', 404)
    request = _serializable_record(request)
    if request['status'] != 'PENDIENTE':
        raise WfmError('La solicitud ya fue resuelta', 409)
    timestamp = datetime.now(timezone.utc).isoformat()
    applied_revision = None
    if decision == 'APROBAR':
        team, plan_date = request['team'], request['requested_date']
        active = 'TRUE' if postgres else '1'
        people = [dict(row) for row in query(
            f'SELECT u.id,u.display_name FROM users u JOIN roles r ON r.id=u.role_id '
            f'WHERE u.active={active} AND r.name=? ORDER BY u.display_name',
            (team,),
        ).fetchall()]
        # Una solicitud siempre parte de la publicación vigente. Un borrador
        # posterior pertenece al supervisor y no debe publicarse implícitamente.
        current = query(
            'SELECT * FROM wfm_revisions WHERE plan_date=? AND team=? AND published=1 ORDER BY revision DESC LIMIT 1',
            (plan_date, team),
        ).fetchone()
        if not current:
            raise WfmError('No existe un horario para aplicar esta solicitud', 409)
        current = dict(current)
        source_revision = request.get('source_revision')
        if source_revision is not None and int(source_revision) != int(current['revision']):
            if data.get('confirm_current_revision') is not True:
                raise WfmError(
                    f'El horario publicado cambió desde la solicitud (revisión {source_revision} → '
                    f'{current["revision"]}). Revisá el horario vigente antes de confirmar.',
                    409,
                )
        plan = normalize_plan(json.loads(current['payload']))
        shift = next((item for item in plan.get('shifts', []) if item.get('user_id') == request['user_id']), None)
        if not shift:
            raise WfmError('La persona no tiene turno en la fecha solicitada', 409)
        if request['request_type'] == 'AUSENCIA':
            segments = shift_segments(shift)
            exception_start = request['requested_start'] if request['requested_start'] is not None else segments[0]['start']
            exception_end = request['requested_end'] if request['requested_end'] is not None else segments[-1]['end']
            affected = []
            for segment in segments:
                start = max(exception_start, segment['start'])
                end = min(exception_end, segment['end'])
                if start < end:
                    affected.append((start, end))
            if not affected:
                raise WfmError('La ausencia no coincide con un bloque de trabajo', 409)
            for index, (start, end) in enumerate(affected, 1):
                shift.setdefault('exceptions', []).append(dict(
                    id=f'request-{request_id}-{index}', type='Ausencia', start=start,
                    end=end, note=request['reason'], source_request_id=request_id,
                ))
        else:
            requested_start, requested_end = request['requested_start'], request['requested_end']
            shift['segments'] = [dict(start=requested_start, end=requested_end)]
            shift['start'], shift['end'] = requested_start, requested_end
            shift['break'] = default_break(shift['segments'], shift.get('break_duration', 1))
            shift['exceptions'] = [
                exception for exception in shift.get('exceptions', [])
                if requested_start <= exception['start'] and exception['end'] <= requested_end
            ]
        settings = load_wfm_settings(query, actor['id'])
        plan = validate(plan, {person['id'] for person in people}, team, settings)
        next_revision = query(
            'SELECT COALESCE(MAX(revision), 0) AS revision FROM wfm_revisions WHERE plan_date=? AND team=?',
            (plan_date, team),
        ).fetchone()
        applied_revision = int(next_revision['revision']) + 1
        query(
            'INSERT INTO wfm_revisions(plan_date,team,revision,published,payload,actor_id,created_at) '
            'VALUES(?,?,?,?,?,?,?)',
            (plan_date, team, applied_revision, 1, json.dumps(plan), actor['id'], timestamp),
        )
        _store_published_plan(query, plan_date, team, applied_revision, plan, actor['id'], timestamp)
    status = 'APROBADA' if decision == 'APROBAR' else 'RECHAZADA'
    query(
        'UPDATE wfm_requests SET status=?,resolution_note=?,reviewed_by=?,applied_revision=?,reviewed_at=? '
        'WHERE request_id=?',
        (status, note or None, actor['id'], applied_revision, timestamp, request_id),
    )
    request.update(
        status=status, resolution_note=note or None, reviewed_by=actor['id'],
        reviewer_name=actor.get('display_name'), applied_revision=applied_revision, reviewed_at=timestamp,
    )
    return request


def _publish_week(query, actor, params, data, postgres):
    """Publica atómicamente las últimas revisiones en borrador de una semana."""
    team = params.get('team')
    if team not in TEAMS:
        raise WfmError('Equipo inválido')
    week_start = day(params.get('week'))
    first_day = date.fromisoformat(week_start)
    if first_day.weekday() != 0:
        raise WfmError('La semana debe comenzar un lunes')
    if not isinstance(data, dict):
        raise WfmError('Publicación semanal inválida')
    if postgres:
        query('SELECT pg_advisory_xact_lock(73139030)')
    else:
        query('BEGIN IMMEDIATE')
    active = 'TRUE' if postgres else '1'
    people = [dict(row) for row in query(
        f'SELECT u.id,u.display_name FROM users u JOIN roles r ON r.id=u.role_id '
        f'WHERE u.active={active} AND r.name=? ORDER BY u.display_name',
        (team,),
    ).fetchall()]
    people_ids = {person['id'] for person in people}
    settings = load_wfm_settings(query, actor['id'])
    requirements = load_requirements(query, team, actor['id'])
    drafts, missing, already_published, alert_messages = [], [], [], []
    expected_revisions = data.get('expected_revisions')
    if expected_revisions is not None and not isinstance(expected_revisions, dict):
        raise WfmError('Las revisiones esperadas de la semana son inválidas')
    for offset in range(7):
        plan_date = (first_day + timedelta(days=offset)).isoformat()
        current = query(
            'SELECT * FROM wfm_revisions WHERE plan_date=? AND team=? ORDER BY revision DESC LIMIT 1',
            (plan_date, team),
        ).fetchone()
        if expected_revisions is not None and plan_date in expected_revisions:
            try:
                expected = integer(expected_revisions[plan_date], 0, 2**31 - 1, 'Revisión esperada')
            except (KeyError, TypeError):
                raise WfmError(f'Revisión esperada inválida para {plan_date}') from None
            actual = int(current['revision']) if current else 0
            if expected != actual:
                raise WfmError(
                    f'El día {plan_date} cambió mientras revisabas la semana '
                    f'(esperabas revisión {expected}, ahora está en {actual}). Recargá antes de publicar.',
                    409,
                )
        if not current:
            missing.append(plan_date)
            continue
        current = dict(current)
        if bool(current['published']):
            already_published.append(plan_date)
            continue
        source_plan, _ = fill_missing_demand(json.loads(current['payload']), requirements, plan_date, team)
        plan = validate(source_plan, people_ids, team, settings)
        alerts = warnings(plan, team)
        if alerts:
            alert_messages.extend(f'{plan_date}: {message}' for message in alerts)
        drafts.append((plan_date, int(current['revision']) + 1, plan))
    if not drafts and not already_published:
        raise WfmError('No hay borradores guardados para publicar en esta semana', 409)
    if alert_messages and data.get('confirm_exceptions') is not True:
        raise WfmError('Revisá y confirmá las advertencias semanales: ' + '; '.join(alert_messages), 409)
    timestamp = datetime.now(timezone.utc).isoformat()
    for plan_date, revision, plan in drafts:
        query(
            'INSERT INTO wfm_revisions(plan_date,team,revision,published,payload,actor_id,created_at) '
            'VALUES(?,?,?,?,?,?,?)',
            (plan_date, team, revision, 1, json.dumps(plan), actor['id'], timestamp),
        )
        _store_published_plan(query, plan_date, team, revision, plan, actor['id'], timestamp)
    return dict(
        team=team, week=week_start, published_count=len(drafts),
        published_dates=[item[0] for item in drafts],
        already_published=already_published, missing_drafts=missing,
        warnings=alert_messages,
    )


def dispatch(db, actor, method, action, params, data=None, postgres=False):
    """El llamador aporta una transacción, autenticación y protección CSRF."""
    def query(sql, args=()):
        return db.execute(sql.replace('?', '%s') if postgres else sql, args)

    if action == 'mine' and method == 'GET':
        start, end = day(params.get('from')), day(params.get('to'))
        if not 0 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 366:
            raise WfmError('El período debe estar entre 0 y 366 días')
        query_start = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        rows = _published_schedules(
            query,
            {'date_from': query_start, 'date_to': end, 'employee_id': str(actor['id'])},
            postgres,
        )
        result = []
        for row in rows:
            plan_date = row['schedule_date']
            if plan_date < start and not row.get('crosses_midnight'):
                continue
            result.append(dict(
                id=row['id'], user_id=row['user_id'], date=plan_date,
                end_date=(date.fromisoformat(plan_date) + timedelta(days=1 if row.get('crosses_midnight') else 0)).isoformat(),
                team=row['team'], revision=row.get('revision'), source=row.get('source', 'wfm'),
                shift_name=row.get('shift_name'), notes=row.get('notes', ''),
                start=row.get('start_slot'), end=row.get('end_slot'), segments=row.get('segments', []),
                break_duration=row.get('break_duration', 0),
                overtime_slots=row.get('overtime_slots', 0), exceptions=row.get('exceptions', []),
                **{'break': row.get('break_slot')},
            ))
        published_days = query(
            'SELECT DISTINCT plan_date FROM wfm_revisions WHERE published=1 AND team=? '
            'AND plan_date>=? AND plan_date<=?',
            (actor.get('role_name'), start, end),
        ).fetchall()
        occupied = {item['date'] for item in result if item.get('date') >= start}
        for record in published_days:
            raw_date = record['plan_date']
            published_date = raw_date.isoformat() if hasattr(raw_date, 'isoformat') else str(raw_date)
            if published_date not in occupied:
                result.append(dict(
                    id=f'free:{published_date}:{actor["id"]}', user_id=actor['id'], date=published_date,
                    end_date=published_date, team=actor.get('role_name'), revision=None, source='wfm',
                    shift_name='Libre publicado', notes='', start=None, end=None, segments=[],
                    break_duration=0, overtime_slots=0, exceptions=[], published_day=True,
                    **{'break': None},
                ))
        return sorted(result, key=lambda s: (s['date'], s['start'] if s['start'] is not None else -1))

    if action == 'requests':
        if method == 'GET':
            return _request_rows(query, actor, params, postgres)
        if method == 'POST':
            if isinstance(data, dict) and data.get('operation') == 'decide':
                return _decide_request(query, actor, data, postgres)
            if isinstance(data, dict) and data.get('operation') == 'cancel':
                return _cancel_request(query, actor, data, postgres)
            return _create_request(query, actor, data, postgres)
        raise WfmError('Operación inválida')

    if not manager(actor):
        raise WfmError('Planificación exclusiva para Supervisor (Administrador conserva acceso completo)', 403)

    if action == 'published':
        if method != 'GET':
            raise WfmError('Operación inválida')
        return _published_schedules(query, params, postgres)

    if action == 'publish-week':
        if method != 'POST':
            raise WfmError('Operación inválida')
        return _publish_week(query, actor, params, data, postgres)

    if action == 'settings':
        if not administrator(actor):
            raise WfmError('La configuración general de WFM es exclusiva del Administrador', 403)
        if method == 'GET':
            return load_wfm_settings(query, actor['id'])
        if method == 'POST':
            settings = validate_wfm_settings(data)
            if postgres:
                query('SELECT pg_advisory_xact_lock(73139030)')
            else:
                query('BEGIN IMMEDIATE')
            timestamp = datetime.now(timezone.utc).isoformat()
            for setting_key, value in settings.items():
                query(
                    'INSERT INTO wfm_settings(setting_key,value,actor_id,updated_at) '
                    'VALUES(?,?,?,?) ON CONFLICT(setting_key) DO UPDATE SET '
                    'value=excluded.value,actor_id=excluded.actor_id,updated_at=excluded.updated_at',
                    (setting_key, value, actor['id'], timestamp),
                )
            return load_wfm_settings(query, actor['id'])
        raise WfmError('Operación inválida')

    team = params.get('team')
    if team not in TEAMS:
        raise WfmError('Equipo inválido')

    if action == 'person' and method == 'GET':
        start, end = day(params.get('from')), day(params.get('to'))
        total_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        if not 0 <= total_days <= 6:
            raise WfmError('La vista semanal debe abarcar entre 1 y 7 días')
        try:
            user_id = int(params.get('user_id'))
        except (TypeError, ValueError):
            raise WfmError('Persona inválida') from None
        people = [dict(r) for r in query(
            f'SELECT u.id,u.display_name FROM users u JOIN roles r ON r.id=u.role_id '
            f'WHERE u.active={"TRUE" if postgres else "1"} AND r.name=? ORDER BY u.display_name',
            (team,),
        ).fetchall()]
        person = next((item for item in people if item['id'] == user_id), None)
        if not person:
            raise WfmError('La persona no pertenece al equipo seleccionado', 404)
        query_start = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        records = query(
            'SELECT * FROM wfm_revisions WHERE published=1 AND plan_date>=? AND plan_date<=? '
            'AND team=? ORDER BY plan_date ASC, revision DESC',
            (query_start, end, team),
        ).fetchall()
        published_days, shifts_by_day = set(), {}
        for record in records:
            raw_day = dict(record)['plan_date']
            plan_day = raw_day.isoformat() if hasattr(raw_day, 'isoformat') else str(raw_day)
            if plan_day in published_days:
                continue
            published_days.add(plan_day)
            payload = normalize_plan(json.loads(dict(record)['payload']))
            shifts_by_day[plan_day] = next(
                (dict(shift) for shift in payload.get('shifts', []) if shift.get('user_id') == user_id),
                None,
            )
        base = next((item for item in weekly_schedule_for_people([person], team, start)), None)
        days = []
        for offset in range(total_days + 1):
            current_day = (date.fromisoformat(start) + timedelta(days=offset)).isoformat()
            previous_day = (date.fromisoformat(current_day) - timedelta(days=1)).isoformat()
            previous_shift = shifts_by_day.get(previous_day)
            days.append(dict(
                date=current_day,
                published=current_day in published_days,
                shift=shifts_by_day.get(current_day),
                carry_in=previous_shift if previous_shift and previous_shift.get('end', 0) > 48 else None,
            ))
        return dict(
            person=person,
            team=team,
            start=start,
            end=end,
            base_day_off=base['day_off'] if base else None,
            days=days,
        )

    if action == 'requirements':
        if method == 'POST':
            requirements = validate_requirements(data)
            if postgres:
                query('SELECT pg_advisory_xact_lock(73139030)')
            else:
                query('BEGIN IMMEDIATE')
            timestamp = datetime.now(timezone.utc).isoformat()
            for weekday, required in enumerate(requirements):
                query(
                    'INSERT INTO wfm_weekly_requirements(team,weekday,required,actor_id,updated_at) '
                    'VALUES(?,?,?,?,?) ON CONFLICT(team,weekday) DO UPDATE SET '
                    'required=excluded.required,actor_id=excluded.actor_id,updated_at=excluded.updated_at',
                    (team, weekday, required, actor['id'], timestamp),
                )
            return dict(team=team, requirements=requirements)
        if method == 'GET':
            return dict(team=team, requirements=load_requirements(query, team, actor['id']))
        raise WfmError('Operación inválida')

    if action != 'plan':
        raise WfmError('Ruta inexistente', 404)
    plan_date = day(params.get('date'))
    if method == 'POST':
        if postgres:
            # Un único cerrojo de planificación evita publicaciones simultáneas perdidas.
            query('SELECT pg_advisory_xact_lock(73139030)')
        else:
            query('BEGIN IMMEDIATE')
    active = 'TRUE' if postgres else '1'
    people = [dict(r) for r in query(f'SELECT u.id,u.display_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.active={active} AND r.name=? ORDER BY u.display_name', (team,)).fetchall()]
    current = query('SELECT * FROM wfm_revisions WHERE plan_date=? AND team=? ORDER BY revision DESC LIMIT 1', (plan_date, team)).fetchone()
    current = dict(current) if current else None
    revision = current['revision'] if current else 0
    published = query('SELECT MAX(revision) AS version FROM wfm_revisions WHERE plan_date=? AND team=? AND published=1', (plan_date, team)).fetchone()
    published_revision = dict(published)['version'] or 0
    requirements = load_requirements(query, team, actor['id'])
    settings = load_wfm_settings(query, actor['id'])
    weekly_schedule = weekly_schedule_for_people(people, team, plan_date)
    if method == 'GET':
        source_plan = json.loads(current['payload']) if current else dict(
            demand=daily_demand(requirements, plan_date, team),
            shifts=default_shifts(weekly_schedule, plan_date, settings),
        )
        plan, demand_filled = fill_missing_demand(source_plan, requirements, plan_date, team)
        return dict(plan, revision=revision, published_revision=published_revision, people=people,
                    requirements=requirements, weekly_schedule=weekly_schedule,
                    settings=settings, demand_filled=demand_filled,
                    window=TEAM_WINDOWS[team], horizon=HORIZON_SLOTS,
                    exception_types=list(EXCEPTION_TYPES), coverage=coverage(plan, team),
                    warnings=warnings(plan, team))
    if method != 'POST' or not isinstance(data, dict):
        raise WfmError('Operación inválida')
    if integer(data.get('revision'), 0, 2**31-1, 'Revisión') != revision:
        changed_by = current.get('actor_id') if current else None
        changed_at = current.get('created_at') if current else None
        detail = f' La versión actual es la revisión {revision}.'
        if changed_by is not None:
            detail += f' Fue guardada por el usuario {changed_by}'
        if changed_at:
            detail += f' el {changed_at}.'
        raise WfmError(
            'Otro supervisor cambió este plan. Recargá antes de guardar; tu borrador sigue visible.' + detail,
            409,
        )
    plan = validate(data, {p['id'] for p in people}, team, settings)
    operation = data.get('operation', 'save')
    if operation not in ('save', 'publish', 'optimize'):
        raise WfmError('Operación inválida')
    if operation == 'optimize':
        plan = optimize(plan, team)
        return dict(plan, revision=revision, published_revision=published_revision, people=people,
                    requirements=requirements, weekly_schedule=weekly_schedule,
                    settings=settings, window=TEAM_WINDOWS[team], horizon=HORIZON_SLOTS,
                    exception_types=list(EXCEPTION_TYPES), coverage=coverage(plan, team),
                    warnings=warnings(plan, team))
    alerts = warnings(plan, team)
    if operation == 'publish' and alerts and data.get('confirm_exceptions') is not True:
        raise WfmError('Revisá y confirmá las advertencias antes de publicar: ' + '; '.join(alerts), 409)
    revision += 1
    timestamp = datetime.now(timezone.utc).isoformat()
    query('INSERT INTO wfm_revisions(plan_date,team,revision,published,payload,actor_id,created_at) VALUES(?,?,?,?,?,?,?)',
          (plan_date, team, revision, int(operation == 'publish'), json.dumps(plan), actor['id'], timestamp))
    if operation == 'publish':
        _store_published_plan(query, plan_date, team, revision, plan, actor['id'], timestamp)
    return dict(plan, revision=revision, published_revision=revision if operation == 'publish' else published_revision,
                 people=people, requirements=requirements, weekly_schedule=weekly_schedule,
                 settings=settings, window=TEAM_WINDOWS[team], horizon=HORIZON_SLOTS,
                 exception_types=list(EXCEPTION_TYPES), coverage=coverage(plan, team),
                 warnings=alerts)
