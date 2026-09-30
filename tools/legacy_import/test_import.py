"""Synthetic tests against a dedicated disposable PostgreSQL database."""
import ast
from contextlib import redirect_stderr, redirect_stdout
import csv
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest

import psycopg
from psycopg.rows import dict_row

from tools.legacy_import.import_csv import Users, RowError, delay_time, insert_row, main, parse_date, transform


class ParsingTests(unittest.TestCase):
    def test_local_time(self):
        self.assertEqual(parse_date('31/12/2025 23:30').isoformat(), '2026-01-01T02:30:00+00:00')
        for value in ('31/02/2025 10:00', '01/01/2024 10:00', '2025-01-01'):
            with self.assertRaises(RowError):
                parse_date(value)

    def test_times(self):
        for first, second in [('Margen de', '90'), ('1,5 horas', ''), ('01:30', ''), ('1 h 30 min', ''), ('90 minutos', '90')]:
            self.assertEqual(delay_time(first, second), ('Margen de', 90))
        self.assertEqual(delay_time('No confirmar tiempos', ''), ('No confirmar tiempos', None))
        for values in [('60', '90'), ('60 a 90', ''), ('No confirmar tiempos', '90'), ('0', ''), ('01:70', '')]:
            with self.assertRaises(RowError):
                delay_time(*values)

    def test_user_ambiguity_and_combined_service(self):
        rows = [{'id': 1, 'username': 'qa1', 'display_name': 'Persona QA'}, {'id': 2, 'username': 'qa2', 'display_name': 'Persona QA'}]
        with self.assertRaises(RowError):
            Users(rows).resolve('Persona QA')
        users = Users(rows, {'Alias QA': 2})
        row = transform('delays', ['01/06/2025 12:00', 'NORMALIZADO', 'SIN Y ML', 'Rio Negro', 'Zona QA', 'Margen de', '90', 'Alias QA'], users, {})
        self.assertEqual([r['service'] for r in row['records']], ['SINIESTROS', 'ML'])
        self.assertEqual(row['resolved']['agent_user_id'], 2)
        self.assertTrue(all(r['normalized_at'] is None for r in row['records']))


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Guard before any write: never use a database other than the synthetic fixture.
        if os.environ.get('DATABASE_URL') != 'postgresql://legacy_test:synthetic_test_only@db:5432/legacy_test':
            raise RuntimeError('Solo ejecutar con compose.test.yaml')
        cls.db = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, row_factory=dict_row)
        tree = ast.parse(Path('app/postgres_server.py').read_text(encoding='utf-8'))
        constants = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'SCHEMA', 'NOTICE_EVENTS_SCHEMA'} for t in node.targets):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
        cls.db.execute(constants['SCHEMA'])
        cls.db.execute(constants['NOTICE_EVENTS_SCHEMA'])
        # Use the current backend's actual delay ALTERs/event DDL, without importing its startup.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'execute' and node.args:
                value = node.args[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    statement = value.value.strip()
                    if statement.startswith('ALTER TABLE delay_zones ADD COLUMN') and 'zone_id' not in statement:
                        cls.db.execute(statement)
                    elif statement.startswith('CREATE TABLE IF NOT EXISTS delay_events'):
                        cls.db.execute(statement)
        cls.db.execute("INSERT INTO roles(id,name) VALUES(1,'QA')")
        cls.db.execute("INSERT INTO users(id,username,display_name,password_hash,role_id) VALUES(1,'qa1','Persona QA Uno','unused',1),(2,'qa2','Persona QA Dos','unused',1)")
        cls.db.execute("ALTER TABLE notices ADD CONSTRAINT test_rejected_task CHECK (task_number <> 'RECHAZAR')")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_simulate_apply_retry_and_row_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath('mapping.json').write_text(json.dumps({'users': {'Alias QA': 1}}))
            notice = ['Fecha y Hora', 'Tarea', 'Teléfono', 'Aviso', 'Para', 'Detalle', 'Comunica', 'Gestiona', 'Estado', 'Comentarios']
            rows = [notice,
                    ['01/05/2025 09:00', '0000123', '099000000', 'Consulta', 'Todos', 'Detalle; con salto\nde línea', 'Alias QA', 'qa2', 'En gestión', 'Comentario histórico'],
                    ['31/02/2025 09:00', 'QA2', '', 'Consulta', 'Todos', 'Incorrecto', 'qa1', '', 'Pendiente', ''],
                    ['01/05/2025 09:00', 'RECHAZAR', '', 'Consulta', 'Todos', 'Rechazo por constraint', 'qa1', '', 'Pendiente', ''],
                    ['01/05/2026 09:00', 'QA3', '', 'Consulta', 'Todos', 'Posterior al rechazo', 'qa1', '', 'Resuelto', 'Cerrado']]
            with root.joinpath('avisos.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                csv.writer(stream, delimiter=';').writerows(rows)
            with root.joinpath('demoras.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                csv.writer(stream, delimiter=';').writerows([
                    ['Fecha', 'Estado', 'Prestación', 'Departamento', 'Zona', 'Mensaje', 'Tiempo', 'Agente'],
                    ['01/05/2025 09:00', 'VIGENTE', 'SIN Y ML', 'Montevideo', 'Zona QA', 'Margen de', '90', 'Alias QA'],
                    ['01/05/2025 10:00', 'NORMALIZADO', 'GRUA', 'Montevideo', 'Zona QA', 'No confirmar tiempos', '', 'qa1']])
            args = ['--input-dir', str(root), '--batch-size', '2']
            log = StringIO()
            with redirect_stdout(log), redirect_stderr(log):
                self.assertEqual(main(args), 2)  # invalid date; dry run makes no writes
                self.assertEqual(self.db.execute('SELECT count(*) n FROM notices').fetchone()['n'], 0)
                self.assertEqual(self.db.execute('SELECT count(*) n FROM audit_events').fetchone()['n'], 0)
                self.assertEqual(main(args + ['--apply']), 2)
                self.assertEqual(main(args + ['--apply']), 2)  # no duplicate successful rows
            self.assertNotIn('099000000', log.getvalue())
            self.assertNotIn('Detalle; con salto', log.getvalue())
            self.assertEqual(self.db.execute('SELECT count(*) n FROM notices').fetchone()['n'], 2)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM delay_zones').fetchone()['n'], 3)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM audit_events').fetchone()['n'], 5)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM notice_events').fetchone()['n'], 2)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM delay_events').fetchone()['n'], 3)
            item = self.db.execute("SELECT * FROM notices WHERE task_number='0000123'").fetchone()
            self.assertEqual(item['phone'], '099000000')
            self.assertEqual(item['managed_by'], 'Persona QA Dos')
            self.assertEqual(item['status'], 'EN_GESTION')
            self.assertEqual(item['comments'], 'Comentario histórico')
            self.assertEqual(item['created_at'].hour, 12)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM delay_zones WHERE expires_at>created_at').fetchone()['n'], 0)

    def test_multiservice_row_is_atomic(self):
        with self.db.transaction(force_rollback=True):
            self.db.execute("ALTER TABLE delay_zones ADD CONSTRAINT test_second_service CHECK (NOT (zone='Rechazo QA' AND service='ML'))")
            before = self.db.execute('SELECT count(*) n FROM delay_zones').fetchone()['n']
            before_audit = self.db.execute('SELECT count(*) n FROM audit_events').fetchone()['n']
            users = Users(self.db.execute('SELECT id,username,display_name FROM users').fetchall())
            row = transform('delays', ['01/06/2025 12:00', 'VIGENTE', 'SIN Y ML', 'Montevideo', 'Rechazo QA', 'Margen de', '90', 'qa1'], users, {})
            with self.assertRaises(psycopg.IntegrityError):
                with self.db.transaction():
                    insert_row(self.db, row, 'demoras.csv', 2)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM delay_zones').fetchone()['n'], before)
            self.assertEqual(self.db.execute('SELECT count(*) n FROM audit_events').fetchone()['n'], before_audit)


if __name__ == '__main__':
    unittest.main()
