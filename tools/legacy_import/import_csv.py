"""ETL histórico de Avisos y Demoras (2025/2026).

ARCHIVOS: desde la raíz del proyecto, colocar los CSV privados en:
  data/legacy_import/avisos.csv      (columnas A:J, con encabezado)
  data/legacy_import/demoras.csv     (columnas A:H, con encabezado)
  data/legacy_import/mapping.json   (opcional: alias de usuarios a IDs reales)
Montar esa carpeta como /imports:ro en Docker. Nunca subirla a Git ni al ZIP.
Ejecutar python -m tools.legacy_import.import_csv --input-dir /imports.
Por defecto SIMULA: solo SELECT; --apply habilita inserciones por lotes.
Usa DATABASE_URL ya configurada dentro del contenedor, nunca una URL por CLI.
Ver README.md para comandos completos, mapeos, pruebas y códigos de salida.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.delays import DELAY_SERVICES, clean_delay, normalized_key
from app.notices import NOTICE_AUDIENCES, NOTICE_STATUSES

SOURCE = 'legacy_csv_v1'
LOCK_ID = 2025092501


class RowError(ValueError):
    """Only messages authored here, never original row content, enter logs."""


def key(value):
    return normalized_key(value).replace('_', ' ').upper()


def parse_date(value, years=(2025, 2026), tz='America/Montevideo'):
    try:
        if not re.fullmatch(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}(?::\d{2})?', value):
            raise ValueError()
        fmt = '%d/%m/%Y %H:%M:%S' if value.count(':') == 2 else '%d/%m/%Y %H:%M'
        result = datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo(tz))
        if result.year not in years:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError:
        raise RowError('FECHA: se requiere DD/MM/YYYY HH:mm dentro de los años habilitados') from None


def parse_minutes(value):
    text = key(value).replace(',', '.')
    if re.fullmatch(r'\d{1,2}:\d{2}', text):
        hours, minutes = map(int, text.split(':'))
        if minutes >= 60:
            raise RowError('TIEMPO: minutos de reloj inválidos')
        amount = Decimal(hours * 60 + minutes)
    else:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(H|HS|HORA|HORAS)(?:\s*(\d+)\s*(?:M|MIN|MINUTO|MINUTOS))?', text)
        if match:
            amount = Decimal(match[1]) * 60 + Decimal(match[3] or '0')
        else:
            match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:M|MIN|MINUTO|MINUTOS)?', text)
            if not match:
                raise RowError('TIEMPO: formato desconocido o rango ambiguo')
            amount = Decimal(match[1])
    if amount != amount.to_integral_value() or not 1 <= amount <= 1440:
        raise RowError('TIEMPO: se requieren minutos enteros entre 1 y 1440')
    return int(amount)


def delay_time(first, second):
    special = {'NO CONFIRMAR TIEMPOS': 'No confirmar tiempos', 'A CONFIRMAR': 'A confirmar'}
    labels, values = [], []
    for text in (first, second):
        if not text:
            continue
        label = key(text)
        if label in special:
            labels.append(special[label])
        elif label not in {'MARGEN DE', 'MINUTOS', 'MIN'}:
            values.append(parse_minutes(re.sub(r'^MARGEN DE\s+', '', label)))
    if labels:
        if values or len(set(labels)) != 1:
            raise RowError('TIEMPO: etiqueta y minutos contradictorios')
        return labels[0], None
    if not values or len(set(values)) != 1:
        raise RowError('TIEMPO: falta un margen o F y G se contradicen')
    return 'Margen de', values[0]


class Users:
    def __init__(self, rows, aliases=None):
        self.by_id = {row['id']: row for row in rows}
        self.names = {}
        for row in rows:
            for name in (row['username'], row['display_name']):
                self.names.setdefault(key(name), set()).add(row['id'])
        self.aliases = {}
        for name, identifier in (aliases or {}).items():
            if type(identifier) is not int or identifier not in self.by_id:
                raise RowError('MAPEO: un alias apunta a un ID de usuario inexistente o inválido')
            normalized = key(name)
            if normalized in self.aliases and self.aliases[normalized] != identifier:
                raise RowError('MAPEO: aliases normalizados contradictorios')
            self.aliases[normalized] = identifier

    def resolve(self, name, optional=False):
        if optional and key(name) in {'', '-', 'SIN ASIGNAR', 'SIN RESPONSABLE'}:
            return None
        normalized = key(name)
        if not normalized:
            raise RowError('USUARIO: falta el creador de la fila')
        ids = {self.aliases[normalized]} if normalized in self.aliases else self.names.get(normalized, set())
        if len(ids) != 1:
            raise RowError('USUARIO: alias desconocido o ambiguo; completar mapping.json con el ID real')
        return self.by_id[next(iter(ids))]


def canonical(value, choices, label):
    matches = [choice for choice in choices if key(choice) == key(value)]
    if not matches:
        raise RowError(label + ': valor no reconocido')
    return matches[0]


def transform(kind, cells, users, mapping, years=(2025, 2026), tz='America/Montevideo'):
    expected = 10 if kind == 'notices' else 8
    cells = [cell.strip() for cell in cells]
    while len(cells) > expected and not cells[-1]:
        cells.pop()
    if len(cells) != expected:
        raise RowError('COLUMNAS: cantidad distinta de ' + str(expected))
    created = parse_date(cells[0], years, tz)
    digest = hashlib.sha256(json.dumps([kind, cells], ensure_ascii=False).encode()).hexdigest()
    correlation = SOURCE + ':' + digest
    if kind == 'notices':
        _, task, phone, reason, audience, detail, creator, assignee, status, comments = cells
        creator = users.resolve(creator)
        assignee = users.resolve(assignee, optional=True)
        audience = mapping.get('audiences', {}).get(key(audience), audience or 'TODOS')
        audience = canonical(audience, NOTICE_AUDIENCES, 'DESTINATARIO')
        status = canonical(status, NOTICE_STATUSES, 'ESTADO')
        if not reason or not detail:
            raise RowError('AVISO: faltan motivo o detalle')
        records = [dict(task_number=task, phone=phone, notice_type=reason, audience=audience,
                        detail=detail, communicated_by=creator['display_name'],
                        managed_by=assignee['display_name'] if assignee else None,
                        status=status, comments=comments, created_at=created, updated_at=created)]
        resolved = {'created_by_user_id': creator['id'], 'assigned_to_user_id': assignee['id'] if assignee else None}
    else:
        _, status, service, department, zone, first, second, creator = cells
        creator = users.resolve(creator)
        status = canonical(status, ('NORMALIZADO', 'VIGENTE'), 'ESTADO')
        service_map = {'SIN': ['SINIESTROS'], 'SIN Y ML': ['SINIESTROS', 'ML']}
        service_map.update(mapping.get('services', {}))
        services = service_map.get(key(service), [service])
        if isinstance(services, str):
            services = [services]
        if not isinstance(services, list) or not services:
            raise RowError('PRESTACIÓN: el mapeo debe ser una lista no vacía')
        services = list(dict.fromkeys(canonical(s, DELAY_SERVICES, 'PRESTACIÓN') for s in services))
        message, minutes = delay_time(first, second)
        records = []
        for service in services:
            try:
                clean = clean_delay(dict(service=service, department=department, zone=zone, message=message, minutes=minutes))
            except ValueError:
                raise RowError('DEMORA: departamento, zona, prestación o minutos inválidos') from None
            records.append(dict(service=clean['service'], department=clean['department'], zone=clean['zone'],
                                message=message, minutes=minutes, status=status, agent=creator['display_name'],
                                created_at=created, normalized_at=None, expires_at=created))
        resolved = {'agent_user_id': creator['id']}
    return dict(kind=kind, records=records, correlation=correlation, creator=creator, resolved=resolved)


def read_rows(path, header=True, encoding='utf-8-sig', delimiter=None):
    with path.open(encoding=encoding, newline='') as stream:
        first = stream.readline()
        if re.fullmatch(r'sep=([;,\t])\s*', first, re.I):
            delimiter = first[4]
        else:
            stream.seek(0)
        start = stream.tell()
        if delimiter is None:
            sample = stream.read(16384)
            stream.seek(start)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=';,\t').delimiter
            except csv.Error:
                raise RowError('CSV: no se detectó separador; indicar --delimiter') from None
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        if header:
            titles = next(reader, [])
            if not titles or not key(titles[0]).startswith('FECHA'):
                raise RowError('CSV: falta encabezado Fecha; para archivos sin encabezado usar --no-header')
        for cells in reader:
            if any(cell.strip() for cell in cells):
                yield reader.line_num, cells


def insert_row(db, row, filename, line):
    kind, records = row['kind'], row['records']
    table = 'notices' if kind == 'notices' else 'delay_zones'
    for index, record in enumerate(records):
        statement = sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING id').format(
            sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, record)),
            sql.SQL(',').join(sql.Placeholder() for _ in record))
        identifier = db.execute(statement, list(record.values())).fetchone()['id']
        actor = row['creator']['display_name']
        note = 'Importación CSV histórica; fecha de cierre/normalización no disponible en el origen.'
        if kind == 'notices':
            db.execute('INSERT INTO notice_events(notice_id,event_type,actor,detail,new_value,comment,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                       (identifier, 'IMPORTADO', actor, note, record['status'], record['comments'], datetime.now(timezone.utc)))
        else:
            db.execute('INSERT INTO delay_events(delay_id,event_type,actor,note,created_at) VALUES(%s,%s,%s,%s,%s)',
                       (identifier, 'IMPORTADO', actor, note, datetime.now(timezone.utc)))
        db.execute('INSERT INTO audit_events(entity,entity_id,action,actor,actor_id,actor_name,detail,after_data,correlation_id,source,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                   ('notice' if kind == 'notices' else 'delay', identifier, 'IMPORTADO', actor,
                    row['creator']['id'], actor, 'Carga histórica CSV',
                    json.dumps({'file': filename, 'line': line, 'original_created_at': record['created_at'].isoformat(),
                                'user_ids': row['resolved'], 'status': record['status']}, ensure_ascii=False),
                    row['correlation'] + (f':{index}' if index else ''), SOURCE, datetime.now(timezone.utc)))


def import_file(db, kind, path, users, mapping, args):
    totals = dict(valid=0, inserted_rows=0, inserted_records=0, duplicates=0, errors=0)
    seen = set()
    source = read_rows(path, not args.no_header, args.encoding, args.delimiter)
    while True:
        batch = []
        for _ in range(args.batch_size):
            try:
                item = next(source)
            except StopIteration:
                break
            except (RowError, csv.Error, UnicodeError):
                print(f'{path.name}: CSV inválido; se detiene este archivo (revisar codificación/estructura)', file=sys.stderr)
                totals['errors'] += 1
                break
            batch.append(item)
        if not batch:
            break
        pending = []
        for line, cells in batch:
            try:
                pending.append((line, transform(kind, cells, users, mapping, args.years, args.timezone)))
                totals['valid'] += 1
            except RowError as error:
                totals['errors'] += 1
                print(f'{path.name}:{line}: {error}', file=sys.stderr)
        with db.transaction():
            if args.apply:
                db.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
            hashes = [row['correlation'] for _, row in pending]
            existing = {item['correlation_id'] for item in db.execute(
                'SELECT correlation_id FROM audit_events WHERE source=%s AND correlation_id=ANY(%s)', (SOURCE, hashes)).fetchall()}
            for line, row in pending:
                fingerprint = row['correlation']
                if fingerprint in existing or fingerprint in seen:
                    totals['duplicates'] += 1
                    continue
                if args.apply:
                    try:
                        with db.transaction():  # SAVEPOINT: a failed row cannot abort the batch.
                            insert_row(db, row, path.name, line)
                    except (psycopg.IntegrityError, psycopg.DataError) as error:
                        totals['errors'] += 1
                        print(f'{path.name}:{line}: BD rechaza la fila (SQLSTATE {error.sqlstate})', file=sys.stderr)
                        continue
                    totals['inserted_rows'] += 1
                    totals['inserted_records'] += len(row['records'])
                seen.add(fingerprint)
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=Path('/imports'))
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--batch-size', type=int, default=500)
    parser.add_argument('--encoding', default='utf-8-sig')
    parser.add_argument('--delimiter', choices=[';', ',', '\t'])
    parser.add_argument('--no-header', action='store_true')
    parser.add_argument('--years', nargs='+', type=int, default=[2025, 2026])
    parser.add_argument('--timezone', default='America/Montevideo')
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 10000:
        parser.error('--batch-size debe estar entre 1 y 10000')
    paths = [(kind, args.input_dir / name) for kind, name in [('notices', 'avisos.csv'), ('delays', 'demoras.csv')]]
    paths = [(kind, path) for kind, path in paths if path.is_file()]
    if not paths:
        parser.error('No hay avisos.csv ni demoras.csv en --input-dir')
    url = os.environ.get('DATABASE_URL')
    if not url:
        parser.error('Falta DATABASE_URL en el contenedor')
    try:
        ZoneInfo(args.timezone)
        mapping_path = args.mapping or args.input_dir / 'mapping.json'
        if args.mapping and not mapping_path.is_file():
            raise RowError('MAPEO: archivo indicado inexistente')
        mapping = json.loads(mapping_path.read_text(encoding='utf-8-sig')) if mapping_path.is_file() else {}
        if not isinstance(mapping, dict) or any(not isinstance(value, dict) for value in mapping.values()):
            raise RowError('MAPEO: se esperan diccionarios users/services/audiences')
        normalized_mapping = {}
        for group, values in mapping.items():
            normalized_mapping[group] = {}
            for name, value in values.items():
                normalized = key(name)
                if normalized in normalized_mapping[group] and normalized_mapping[group][normalized] != value:
                    raise RowError('MAPEO: aliases normalizados contradictorios')
                normalized_mapping[group][normalized] = value
        mapping = normalized_mapping
        with psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=10) as db:
            if not args.apply:
                db.execute('SET default_transaction_read_only=on')
            users = Users(db.execute('SELECT id,username,display_name FROM users').fetchall(), mapping.get('users'))
            print('APLICAR: commits por lote; no es una transacción global' if args.apply else 'SIMULACIÓN: sin escrituras')
            errors = 0
            for kind, path in paths:
                counts = import_file(db, kind, path, users, mapping, args)
                print(json.dumps({'file': path.name, **counts}))
                errors += counts['errors']
            return 2 if errors else 0
    except (psycopg.Error, OSError, ValueError, LookupError) as error:
        # Do not print exception details: PostgreSQL errors can embed row values/DSNs.
        detail = str(error) if isinstance(error, RowError) else type(error).__name__
        print(f'ETL detenido: {detail}. Revisar conexión/esquema/mapa. Los lotes ya confirmados permanecen; se puede reintentar.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
