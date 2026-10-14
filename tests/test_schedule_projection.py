"""Lectura de horarios con datos sintéticos; no abre bases operativas."""
import json
import os
import sqlite3
import unittest

import psycopg
from psycopg.rows import dict_row

from app import wfm
from app.scheduling import find_schedule_conflict, schedule_interval


class ScheduleProjectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript(wfm.SCHEMA + """
            CREATE TABLE roles(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE users(id INTEGER PRIMARY KEY, display_name TEXT, role_id INTEGER, active INTEGER);
            CREATE TABLE work_schedules(id INTEGER PRIMARY KEY, user_id INTEGER, schedule_date TEXT,
                week_start TEXT, role_name TEXT, shift_name TEXT, start_time TEXT, end_time TEXT,
                notes TEXT, created_by TEXT, created_at TEXT, updated_at TEXT);
            INSERT INTO roles VALUES(1,'Telefonista');
            INSERT INTO users VALUES(1,'Persona activa',1,1),(2,'Otra persona activa',1,1),
                (3,'Persona inactiva',1,0);
        """)

    def tearDown(self):
        self.db.close()

    def view(self, **params):
        return wfm._published_schedules(self.db.execute, params, False)

    def revision(self, day, number, published, shifts):
        self.db.execute(
            'INSERT INTO wfm_revisions VALUES(?,?,?,?,?,?,?)',
            (day, 'Telefonista', number, int(published), json.dumps({'shifts': shifts}), 1,
             f'{day}T12:00:00Z'),
        )

    def test_last_publication_beats_stale_projection_draft_and_legacy(self):
        day = '2026-12-28'
        old = {'user_id': 1, 'start': 16, 'end': 29, 'segments': [{'start': 16, 'end': 29}],
               'break': 22, 'break_duration': 1, 'exceptions': []}
        latest = {'user_id': 2, 'start': 18, 'end': 31, 'segments': [{'start': 18, 'end': 31}],
                  'break': 24, 'break_duration': 1,
                  'exceptions': [{'id': 'training', 'type': 'Capacitación', 'start': 26, 'end': 27}]}
        self.revision(day, 1, True, [old])
        self.revision(day, 2, True, [latest])
        self.revision(day, 3, False, [old])
        self.db.execute('INSERT INTO wfm_published_plans VALUES(?,?,?,?,?)',
                        (day, 'Telefonista', 1, 1, f'{day}T12:00:00Z'))
        self.db.execute('INSERT INTO wfm_published_shifts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (day, 'Telefonista', 1, 1, 16, 29, json.dumps(old['segments']), 22,
                         1, 0, '[]', 1, f'{day}T12:00:00Z'))
        self.db.execute("INSERT INTO work_schedules VALUES(7,2,'2026-12-28','2026-12-28',"
                        "'Telefonista','Histórico','08:00','14:30','Anterior','Supervisor','2026-12-01','2026-12-01')")
        visible = self.view(week=day)
        self.assertEqual([(row['user_id'], row['revision'], row['source']) for row in visible],
                         [(2, 2, 'wfm')])
        self.assertEqual(visible[0]['break_slot'], 24)
        self.assertEqual(visible[0]['exceptions'][0]['type'], 'Capacitación')
        with_states = self.view(week=day, include_free_days='1')
        self.assertEqual(len(with_states), 2)
        self.assertTrue(all(row['source'] != 'draft' for row in with_states))
        self.assertEqual({row['user_id'] for row in with_states if row.get('published_day')}, {1})

    def test_draft_free_unpublished_history_and_inactive_people(self):
        self.revision('2026-12-30', 1, False, [])
        self.revision('2026-12-31', 1, True, [])
        self.db.execute("INSERT INTO work_schedules VALUES(8,3,'2026-12-29','2026-12-28',"
                        "'Telefonista','Mañana','08:00','12:00','Primero','Supervisor','2026-12-01','2026-12-01')")
        self.db.execute("INSERT INTO work_schedules VALUES(9,3,'2026-12-29','2026-12-28',"
                        "'Telefonista','Tarde','14:00','18:00','Segundo','Supervisor','2026-12-01','2026-12-01')")
        rows = self.view(week='2026-12-28', include_free_days='1')
        historical = [row for row in rows if row['user_id'] == 3 and row['schedule_date'] == '2026-12-29']
        self.assertEqual([row['id'] for row in historical], ['legacy:8', 'legacy:9'])
        self.assertEqual({row['display_name'] for row in historical}, {'Persona inactiva'})
        self.assertTrue(any(row.get('draft_day') for row in rows if row['schedule_date'] == '2026-12-30'))
        self.assertTrue(any(row.get('published_day') for row in rows if row['schedule_date'] == '2026-12-31'))
        self.assertFalse(any(row['schedule_date'] == '2027-01-01' for row in rows))

    def test_night_interval_crosses_year_and_does_not_overlap_split_daytime(self):
        first, last = schedule_interval('2026-12-31', '22:00', '06:00')
        self.assertEqual((first.isoformat(), last.isoformat()),
                         ('2026-12-31T22:00:00', '2027-01-01T06:00:00'))
        self.assertEqual(schedule_interval('2027-01-01', '08:00', '12:00')[0].day, 1)

    def test_multiple_daily_records_and_overnight_conflicts(self):
        records = [dict(id=1, schedule_date='2026-12-31', shift_name='Mañana',
                        start_time='08:00', end_time='12:00')]
        self.assertIsNone(find_schedule_conflict(records, '2026-12-31', 'Tarde',
                                                 '14:00', '18:00'))
        self.assertEqual(find_schedule_conflict(records, '2026-12-31', 'Mediodía',
                                                '11:00', '15:00')[0], 'overlap')
        night = dict(id=2, schedule_date='2026-12-31', shift_name='Noche',
                     start_time='22:00', end_time='06:00')
        self.assertEqual(find_schedule_conflict([night], '2027-01-01', 'Temprano',
                                                '05:00', '08:00')[0], 'overlap')
        self.assertIsNone(find_schedule_conflict([night], '2027-01-01', 'Mañana',
                                                 '08:00', '12:00'))


@unittest.skipUnless(os.getenv('DATABASE_URL'), 'requiere PostgreSQL temporal')
class SchedulePostgresProjectionTests(unittest.TestCase):
    def test_full_team_and_publication_priority(self):
        from app.postgres_server import complete_schedules

        with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as database:
            for table in ('users', 'roles', 'work_schedules', 'wfm_revisions',
                          'wfm_published_plans', 'wfm_published_shifts'):
                database.execute(f'CREATE TEMP TABLE {table} AS SELECT * FROM public.{table} WHERE FALSE')
            database.execute("INSERT INTO roles(id,name) VALUES(1,'Telefonista')")
            database.execute("INSERT INTO users(id,display_name,role_id,active) VALUES"
                             "(1,'Activa',1,TRUE),(2,'Otra activa',1,TRUE),(3,'Inactiva',1,FALSE)")
            current = {'user_id': 2, 'start': 18, 'end': 31,
                       'segments': [{'start': 18, 'end': 31}], 'break': 24,
                       'break_duration': 1, 'exceptions': []}
            database.execute("INSERT INTO wfm_revisions(plan_date,team,revision,published,payload,actor_id,created_at)"
                             " VALUES('2026-12-28','Telefonista',2,1,%s,1,'2026-12-28T12:00:00Z')",
                             (json.dumps({'shifts': [current]}),))
            database.execute("INSERT INTO wfm_revisions(plan_date,team,revision,published,payload,actor_id,created_at)"
                             " VALUES('2026-12-28','Telefonista',3,0,%s,1,'2026-12-28T13:00:00Z')",
                             (json.dumps({'shifts': []}),))
            database.execute("INSERT INTO wfm_published_plans(plan_date,team,revision,actor_id,published_at)"
                             " VALUES('2026-12-28','Telefonista',1,1,'2026-12-28T11:00:00Z')")
            database.execute("INSERT INTO wfm_published_shifts(plan_date,team,user_id,revision,start_slot,end_slot,segments,break_slot,break_duration,overtime_slots,exceptions,actor_id,published_at)"
                             " VALUES('2026-12-28','Telefonista',1,1,16,29,%s,22,1,0,'[]',1,'2026-12-28T11:00:00Z')",
                             (json.dumps([{'start': 16, 'end': 29}]),))
            database.execute("INSERT INTO work_schedules(id,user_id,schedule_date,week_start,role_name,shift_name,start_time,end_time,notes,created_by,created_at,updated_at)"
                             " VALUES(9,3,'2026-12-29','2026-12-28','Telefonista','Noche','22:00','06:00','Histórico','Prueba','2026-12-01','2026-12-01')")
            rows = complete_schedules(database, {'week': '2026-12-28'})
            self.assertEqual([(row['user_id'], row['revision']) for row in rows if row['schedule_date'] == '2026-12-28'], [(2, 2)])
            self.assertEqual([(row['display_name'], row['end_slot']) for row in rows if row['schedule_date'] == '2026-12-29'],
                             [('Inactiva', 60)])
            self.assertEqual(len(rows), 2)


if __name__ == '__main__':
    unittest.main()
