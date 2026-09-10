"""Primitivas WFM para jornadas nocturnas, segmentos y mermas.

Los slots son intervalos semiabiertos de 30 minutos relativos al día de inicio.
El horizonte de 72 slots cubre el día de inicio y las primeras 12 horas del día
siguiente. Las funciones aceptan turnos legacy con ``start``/``end``.
"""
import copy

HORIZON_SLOTS = 72
MAX_SEGMENTS = 8
MAX_EXCEPTIONS = 32
EXCEPTION_TYPES = ('Reunión', 'Capacitación', 'Licencia', 'Ausencia')


def shift_segments(shift):
    source = shift.get('segments')
    if isinstance(source, list) and source:
        return [dict(segment) for segment in source]
    start, end = shift.get('start'), shift.get('end')
    if isinstance(start, int) and isinstance(end, int):
        if end <= start and end <= 48:
            end += 48
        return [dict(start=start, end=end)]
    return []


def canonical_segments(segments):
    """Ordena y une únicamente fragmentos contiguos."""
    ordered = sorted((dict(segment) for segment in segments), key=lambda item: (item['start'], item['end']))
    result = []
    for segment in ordered:
        if result and segment['start'] == result[-1]['end']:
            result[-1]['end'] = segment['end']
        else:
            result.append(segment)
    return result


def shift_bounds(shift):
    segments = shift_segments(shift)
    return (segments[0]['start'], segments[-1]['end']) if segments else (None, None)


def segment_containing(shift, start, duration=1):
    end = start + duration
    return next(
        (segment for segment in shift_segments(shift) if segment['start'] <= start and end <= segment['end']),
        None,
    )


def overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def works_at(shift, slot):
    return any(segment['start'] <= slot < segment['end'] for segment in shift_segments(shift))


def exception_at(shift, slot):
    return next(
        (
            exception for exception in shift.get('exceptions', [])
            if exception['start'] <= slot < exception['end']
        ),
        None,
    )


def operational_at(shift, slot):
    if not works_at(shift, slot):
        return False
    break_duration = shift.get('break_duration', 1)
    if shift.get('break') is not None and shift['break'] <= slot < shift['break'] + break_duration:
        return False
    return exception_at(shift, slot) is None


def working_slots(shift):
    return sum(segment['end'] - segment['start'] for segment in shift_segments(shift))


def operational_slots(shift):
    segments = shift_segments(shift)
    if not segments:
        return 0
    return sum(operational_at(shift, slot) for slot in range(segments[0]['start'], segments[-1]['end']))


def default_break(segments, duration=1):
    if duration <= 0:
        return None
    candidates = [segment for segment in segments if segment['end'] - segment['start'] >= duration + 2]
    if not candidates:
        return segments[0]['start']
    segment = max(candidates, key=lambda item: item['end'] - item['start'])
    return segment['start'] + max(1, (segment['end'] - segment['start'] - duration) // 2)


def normalize_plan(plan, horizon=HORIZON_SLOTS):
    """Convierte una instantánea legacy a la representación vigente en memoria."""
    result = copy.deepcopy(plan)
    demand = result.get('demand')
    if isinstance(demand, list) and len(demand) < horizon:
        result['demand'] = demand + [None] * (horizon - len(demand))
    for shift in result.get('shifts', []):
        segments = canonical_segments(shift_segments(shift))
        if segments:
            shift['segments'] = segments
            shift['start'], shift['end'] = segments[0]['start'], segments[-1]['end']
            shift.setdefault('break_duration', 1)
            shift.setdefault('break', default_break(segments, shift['break_duration']))
            shift.setdefault('overtime_slots', 0)
        shift.setdefault('exceptions', [])
    return result
