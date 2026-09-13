"""Pruebas WFM aisladas: nunca abre centro_operativo.db."""
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch
from app import wfm


class WfmTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript(wfm.SCHEMA + '''
        CREATE TABLE roles(id INTEGER,name TEXT);
        CREATE TABLE users(id INTEGER,display_name TEXT,role_id INTEGER,active INTEGER);
        CREATE TABLE work_schedules(
          id INTEGER PRIMARY KEY, user_id INTEGER, schedule_date TEXT, week_start TEXT,
          role_name TEXT, shift_name TEXT, start_time TEXT, end_time TEXT, notes TEXT,
          created_by TEXT, created_at TEXT, updated_at TEXT);
        INSERT INTO roles VALUES(1,'Telefonista'),(2,'Supervisor'),(3,'Administrador');
        INSERT INTO users VALUES(1,'Agente de prueba',1,1),(2,'Supervisor de prueba',2,1);
        ''')
        self.actor = dict(id=2, role_name='Supervisor', display_name='Supervisor de prueba')
        self.params = dict(date='2026-09-08', team='Telefonista')
        self.plan = dict(revision=0, demand=[0]*48, shifts=[dict(user_id=1, start=16)])

    def tearDown(self):
        self.db.close()

    def test_existing_request_table_is_migrated_additively(self):
        old = sqlite3.connect(':memory:')
        try:
            old.execute('CREATE TABLE wfm_requests(request_id TEXT PRIMARY KEY,status TEXT)')
            old.execute("INSERT INTO wfm_requests VALUES('old','PENDIENTE')")
            wfm.ensure_schema(old)
            columns={row[1] for row in old.execute('PRAGMA table_info(wfm_requests)').fetchall()}
            self.assertTrue(set(wfm.WFM_REQUEST_COLUMNS).issubset(columns))
            self.assertEqual(old.execute('SELECT status FROM wfm_requests WHERE request_id=\'old\'').fetchone()[0],'PENDIENTE')
        finally:
            old.close()

    def test_missing_weekly_template_is_a_valid_empty_template(self):
        with patch.object(type(wfm.WEEKLY_TEMPLATE_PATH), 'read_text', side_effect=FileNotFoundError):
            template = wfm.weekly_template('Telefonista')
        self.assertEqual(template, {})
        self.assertEqual(wfm.weekly_schedule_for_people([], 'Telefonista'), [])

    def call(self, method='POST', data=None, actor=None, action='plan', params=None):
        with self.db:
            return wfm.dispatch(self.db, actor or self.actor, method, action, params or self.params, data or self.plan)

    def test_default_six_hours_thirty_includes_break(self):
        s=self.call()['shifts'][0]
        self.assertEqual((s['start'],s['break'],s['end']),(16,22,29))
        self.assertEqual(sum(r['operational'] for r in wfm.coverage(dict(demand=[0]*48,shifts=[s]))),12)

    def test_weekly_requirements_seed_and_apply_to_new_date(self):
        initial=self.call('GET')
        self.assertEqual(initial['requirements'],[3]*7)
        self.assertEqual(initial['demand'][:11],[0]*11)
        self.assertEqual(initial['demand'][11:44],[3]*33)
        self.assertEqual(initial['demand'][44:],[0]*28)
        saved=self.call('POST',data={'requirements':[1,2,3,4,5,6,7]},action='requirements')
        self.assertEqual(saved['requirements'],[1,2,3,4,5,6,7])
        next_day=self.call('GET',params={'date':'2026-09-14','team':'Telefonista'})
        self.assertEqual(next_day['demand'][11:44],[1]*33)

    def test_legacy_demand_is_completed_without_rewriting_until_save(self):
        legacy=copy.deepcopy(self.plan)
        legacy['demand'][20]=None
        self.call(data=legacy)
        loaded=self.call('GET')
        self.assertTrue(loaded['demand_filled'])
        self.assertEqual(loaded['demand'][20],3)
        self.assertNotIn(None,loaded['demand'])
        stored=self.db.execute('SELECT payload FROM wfm_revisions WHERE revision=1').fetchone()['payload']
        self.assertIsNone(json.loads(stored)['demand'][20])

    def test_administrator_can_change_global_shift_and_break_defaults(self):
        admin=dict(id=3,role_name='Administrador')
        current=self.call('GET',actor=admin,action='settings',params={})
        self.assertEqual((current['shift_minutes'],current['break_minutes']),(390,30))
        updated=self.call('POST',actor=admin,action='settings',params={},data={'shift_minutes':480,'break_minutes':60})
        self.assertEqual((updated['shift_slots'],updated['break_slots']),(16,2))
        plan=self.call('POST',actor=admin,params={'date':'2026-09-15','team':'Telefonista'},data={'revision':0,'demand':[0]*48,'shifts':[{'user_id':1,'start':11}]})
        self.assertEqual((plan['shifts'][0]['break'],plan['shifts'][0]['break_duration'],plan['shifts'][0]['end']),(18,2,27))
        with self.assertRaises(wfm.WfmError) as err:self.call('GET',actor=self.actor,action='settings',params={})
        self.assertEqual(err.exception.status,403)

    def test_dated_weekly_template_preserves_daily_times_overtime_and_statuses(self):
        self.db.executescript("""
        INSERT INTO users VALUES(3,'Victoria Addiego',1,1);
        INSERT INTO users VALUES(4,'Alejandra Ferreira',1,1);
        INSERT INTO users VALUES(5,'Dana Britos',1,1);
        """)
        monday=self.call('GET',params={'date':'2026-09-07','team':'Telefonista'})
        victoria=next(s for s in monday['shifts'] if s['user_id']==3)
        alejandra=next(s for s in monday['shifts'] if s['user_id']==4)
        self.assertEqual((victoria['start'],victoria['end'],victoria['break']),(11,24,17))
        self.assertEqual((alejandra['start'],alejandra['end'],alejandra['break'],alejandra['break_duration']),(19,27,None,0))
        self.assertEqual(sum(r['operational'] for r in wfm.coverage({'demand':[0]*72,'shifts':[alejandra]})),8)
        tuesday=self.call('GET',params={'date':'2026-09-08','team':'Telefonista'})
        victoria=next(s for s in tuesday['shifts'] if s['user_id']==3)
        self.assertEqual((victoria['start'],victoria['end'],victoria['break']),(13,26,19))
        friday=self.call('GET',params={'date':'2026-09-11','team':'Telefonista'})
        victoria=next(s for s in friday['shifts'] if s['user_id']==3)
        self.assertEqual((victoria['end'],victoria['overtime_slots']),(26,2))
        dana=next(item for item in friday['weekly_schedule'] if item['user_id']==5)
        self.assertEqual(dana['day_status'],'Día por Estudio')
        self.assertNotIn(5,{s['user_id'] for s in friday['shifts']})
        sunday=self.call('GET',params={'date':'2026-09-13','team':'Telefonista'})
        self.assertNotIn(3,{s['user_id'] for s in sunday['shifts']})

    def test_complete_supplied_week_loads_twenty_people_and_all_daily_variants(self):
        source=wfm.weekly_template('Telefonista')
        for user_id,item in enumerate(source['people'],10):
            self.db.execute('INSERT INTO users VALUES(?,?,1,1)',(user_id,item['name']))
        expected_counts=[20,20,16,16,14,12,12]
        total_shifts=total_overtime=no_breaks=0
        for offset,expected in enumerate(expected_counts):
            plan_date=f'2026-09-{7+offset:02d}'
            plan=self.call('GET',params={'date':plan_date,'team':'Telefonista'})
            self.assertEqual(len(plan['shifts']),expected)
            total_shifts+=len(plan['shifts'])
            total_overtime+=sum(shift['overtime_slots'] for shift in plan['shifts'])
            no_breaks+=sum(shift['break_duration']==0 and shift['break'] is None for shift in plan['shifts'])
        self.assertEqual((total_shifts,total_overtime,no_breaks),(110,32,15))

    def test_team_windows_limit_phone_and_allow_full_planner_day(self):
        phone=copy.deepcopy(self.plan)
        phone['shifts'][0].update({'start':10,'end':23,'break':16})
        with self.assertRaises(wfm.WfmError):wfm.validate(phone,{1},'Telefonista')
        planner=copy.deepcopy(self.plan)
        planner['shifts'][0].update({'start':0,'end':48,'break':6})
        self.assertEqual(wfm.validate(planner,{1},'Planificador')['shifts'][0]['end'],48)

    def test_midnight_shift_uses_next_day_slots(self):
        plan=dict(demand=[0]*72,shifts=[dict(user_id=1,start=44,end=12,**{'break':52})])
        validated=wfm.validate(plan,{1},'Telefonista')
        shift=validated['shifts'][0]
        self.assertEqual((shift['start'],shift['end']), (44,60))
        self.assertEqual(shift['segments'],[{'start':44,'end':60}])
        self.assertEqual(wfm.coverage(validated,'Telefonista')[50]['operational'],1)
        self.assertEqual(wfm.coverage(validated,'Telefonista')[52]['operational'],0)

    def test_split_shift_and_exception_reduce_coverage(self):
        plan=dict(demand=[0]*72,shifts=[dict(
            user_id=1,segments=[{'start':16,'end':20},{'start':24,'end':33}],
            **{'break':27},exceptions=[{'id':'meeting','type':'Reunión','start':18,'end':20}],
        )])
        validated=wfm.validate(plan,{1},'Telefonista')
        coverage=wfm.coverage(validated,'Telefonista')
        self.assertEqual(len(validated['shifts'][0]['segments']),2)
        self.assertEqual(coverage[17]['operational'],1)
        self.assertEqual(coverage[18]['operational'],0)
        self.assertEqual(coverage[22]['operational'],0)
        self.assertEqual(coverage[25]['operational'],1)

    def test_draft_not_visible_published_snapshot_stays(self):
        self.call()
        agent=dict(id=1,role_name='Telefonista')
        period={'from':'2026-09-01','to':'2026-09-30'}
        self.assertEqual(self.call('GET',actor=agent,action='mine',params=period),[])
        self.plan.update(revision=1,operation='publish')
        self.call()
        self.plan.update(revision=2,operation='save')
        self.plan['shifts'][0]['break']=23
        self.call()
        mine=self.call('GET',actor=agent,action='mine',params=period)
        self.assertEqual(mine[0]['break'],22)
        self.assertEqual(len(self.db.execute('SELECT * FROM wfm_revisions').fetchall()),3)

    def test_publish_complete_week_is_atomic_and_keeps_history(self):
        for offset in range(7):
            plan_date=f'2026-09-{7+offset:02d}'
            self.call('POST',params={'date':plan_date,'team':'Telefonista'},data=copy.deepcopy(self.plan))
        result=self.call(
            'POST', action='publish-week',
            params={'week':'2026-09-07','team':'Telefonista'},
            data={'confirm_exceptions':True},
        )
        self.assertEqual(result['published_count'],7)
        self.assertEqual(result['missing_drafts'],[])
        rows=self.db.execute(
            'SELECT plan_date,revision,published FROM wfm_revisions ORDER BY plan_date,revision'
        ).fetchall()
        self.assertEqual(len(rows),14)
        self.assertTrue(all(rows[index]['published']==0 and rows[index+1]['published']==1 for index in range(0,14,2)))
        self.assertEqual(self.db.execute('SELECT COUNT(*) total FROM wfm_published_plans').fetchone()['total'],7)
        self.assertEqual(self.db.execute('SELECT COUNT(*) total FROM wfm_published_shifts').fetchone()['total'],7)
        published=self.call(
            'GET',action='published',
            params={'week':'2026-09-07','team':'Telefonista'},
        )
        self.assertEqual(len(published),7)
        self.assertEqual(
            (published[0]['schedule_date'],published[0]['start_time'],published[0]['end_time'],published[0]['break_slot']),
            ('2026-09-07','08:00','14:30',22),
        )

    def test_publish_complete_week_rolls_back_if_one_draft_is_invalid(self):
        for offset in range(7):
            plan_date=f'2026-09-{7+offset:02d}'
            self.call('POST',params={'date':plan_date,'team':'Telefonista'},data=copy.deepcopy(self.plan))
        broken=copy.deepcopy(self.plan)
        broken.update(revision=1,demand=[0]*72,shifts=[{'user_id':999,'start':16}])
        self.db.execute(
            'UPDATE wfm_revisions SET payload=? WHERE plan_date=? AND team=? AND revision=1',
            (json.dumps(broken),'2026-09-10','Telefonista'),
        )
        self.db.commit()
        with self.assertRaises(wfm.WfmError):
            self.call(
                'POST',action='publish-week',
                params={'week':'2026-09-07','team':'Telefonista'},
                data={'confirm_exceptions':True},
            )
        published=self.db.execute('SELECT COUNT(*) total FROM wfm_revisions WHERE published=1').fetchone()['total']
        self.assertEqual(published,0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) total FROM wfm_published_plans').fetchone()['total'],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) total FROM wfm_published_shifts').fetchone()['total'],0)

    def test_republish_replaces_current_projection_and_preserves_revisions(self):
        first=copy.deepcopy(self.plan)
        first['operation']='publish'
        self.call(data=first)
        draft=copy.deepcopy(self.plan)
        draft.update(revision=1,operation='save')
        draft['shifts'][0]['start']=18
        self.call(data=draft)
        final=copy.deepcopy(draft)
        final.update(revision=2,operation='publish')
        self.call(data=final)
        projected=self.db.execute('SELECT * FROM wfm_published_shifts').fetchall()
        self.assertEqual(len(projected),1)
        self.assertEqual((projected[0]['start_slot'],projected[0]['revision']),(18,3))
        self.assertEqual(self.db.execute('SELECT COUNT(*) total FROM wfm_revisions').fetchone()['total'],3)
        visible=self.call('GET',action='published',params={'week':'2026-09-07','team':'Telefonista'})
        self.assertEqual((len(visible),visible[0]['start_time'],visible[0]['revision']),(1,'09:00',3))

    def test_published_view_migrates_historical_revisions_on_read(self):
        plan=wfm.validate(self.plan,{1},'Telefonista')
        self.db.execute(
            'INSERT INTO wfm_revisions VALUES(?,?,?,?,?,?,?)',
            ('2026-09-08','Telefonista',1,1,json.dumps(plan),2,'2026-09-08T12:00:00+00:00'),
        )
        visible=self.call('GET',action='published',params={'week':'2026-09-07','q':'Agente de prueba'})
        self.assertEqual(len(visible),1)
        self.assertEqual((visible[0]['display_name'],visible[0]['revision']),('Agente de prueba',1))

    def test_published_history_accepts_open_range_and_rejects_inverted_dates(self):
        published=copy.deepcopy(self.plan)
        published['operation']='publish'
        self.call(data=published)
        visible=self.call('GET',action='published',params={'q':'Agente de prueba'})
        self.assertEqual(len(visible),1)
        with self.assertRaises(wfm.WfmError):
            self.call('GET',action='published',params={'date_from':'2026-09-10','date_to':'2026-09-01'})

    def test_manager_can_view_person_published_week(self):
        published=copy.deepcopy(self.plan)
        published['operation']='publish'
        self.call(data=published)
        view=self.call(
            'GET',
            action='person',
            params={'from':'2026-09-08','to':'2026-09-14','team':'Telefonista','user_id':'1'},
        )
        self.assertEqual(view['person']['id'],1)
        self.assertEqual(len(view['days']),7)
        first=next(day for day in view['days'] if day['date']=='2026-09-08')
        self.assertTrue(first['published'])
        self.assertEqual(first['shift']['start'],16)
        with self.assertRaises(wfm.WfmError) as err:
            self.call('GET', actor=dict(id=1,role_name='Telefonista'), action='person', params={'from':'2026-09-08','to':'2026-09-14','team':'Telefonista','user_id':'1'})
        self.assertEqual(err.exception.status,403)

    def test_permissions_and_own_only(self):
        for role in ('Telefonista','Planificador','Otro'):
            with self.assertRaises(wfm.WfmError) as err:self.call('GET',actor=dict(id=1,role_name=role))
            self.assertEqual(err.exception.status,403)
        self.plan.update(operation='publish')
        self.call()
        self.assertEqual(self.call('GET',action='mine',params={'from':'2026-09-08','to':'2026-09-08'}),[])

    def test_agent_request_approval_publishes_absence(self):
        published=copy.deepcopy(self.plan);published['operation']='publish'
        self.call(data=published)
        agent=dict(id=1,role_name='Telefonista')
        request=self.call('POST',actor=agent,action='requests',params={},data={
            'request_type':'AUSENCIA','requested_date':'2026-09-08','reason':'Consulta médica',
        })
        pending=self.call('GET',action='requests',params={'status':'PENDIENTE','team':'Telefonista'})
        self.assertEqual(pending[0]['request_id'],request['request_id'])
        decided=self.call('POST',action='requests',params={},data={
            'operation':'decide','request_id':request['request_id'],'decision':'APROBAR',
            'resolution_note':'Aprobada por cobertura',
        })
        self.assertEqual((decided['status'],decided['applied_revision']),('APROBADA',2))
        payload=json.loads(self.db.execute('SELECT payload FROM wfm_revisions WHERE revision=2').fetchone()['payload'])
        self.assertEqual(payload['shifts'][0]['exceptions'][0]['type'],'Ausencia')
        self.assertEqual(sum(row['operational'] for row in wfm.coverage(payload,'Telefonista')),0)
        projected=self.call('GET',action='published',params={'week':'2026-09-07','employee_id':'1'})
        self.assertEqual(projected[0]['exceptions'][0]['type'],'Ausencia')
        self.assertEqual(projected[0]['revision'],2)

    def test_full_day_absence_on_split_shift_creates_one_exception_per_segment(self):
        published=copy.deepcopy(self.plan)
        published['shifts'][0]['segments']=[{'start':16,'end':20},{'start':22,'end':31}]
        published['shifts'][0]['start']=16
        published['shifts'][0]['end']=31
        published['shifts'][0]['break']=25
        published['operation']='publish'
        published['confirm_exceptions']=True
        self.call(data=published)
        agent=dict(id=1,role_name='Telefonista')
        request=self.call('POST',actor=agent,action='requests',params={},data={
            'request_type':'AUSENCIA','requested_date':'2026-09-08','reason':'Ausencia completa',
        })
        decided=self.call('POST',action='requests',params={},data={
            'operation':'decide','request_id':request['request_id'],'decision':'APROBAR',
        })
        payload=json.loads(self.db.execute('SELECT payload FROM wfm_revisions WHERE revision=2').fetchone()['payload'])
        exceptions=payload['shifts'][0]['exceptions']
        self.assertEqual([(item['start'],item['end']) for item in exceptions],[(16,20),(22,31)])
        self.assertEqual(decided['applied_revision'],2)

    def test_request_approval_keeps_newer_draft_out_of_published_revision(self):
        published=copy.deepcopy(self.plan)
        published['operation']='publish'
        self.call(data=published)
        draft=copy.deepcopy(self.plan)
        draft.update(revision=1,operation='save')
        draft['demand'][11]=7
        draft['shifts'][0]['start']=18
        self.call(data=draft)
        agent=dict(id=1,role_name='Telefonista')
        request=self.call('POST',actor=agent,action='requests',params={},data={
            'request_type':'AUSENCIA','requested_date':'2026-09-08','reason':'Ausencia',
        })
        self.call('POST',action='requests',params={},data={
            'operation':'decide','request_id':request['request_id'],'decision':'APROBAR',
        })
        payload=json.loads(self.db.execute('SELECT payload FROM wfm_revisions WHERE revision=3 AND published=1').fetchone()['payload'])
        self.assertEqual(payload['demand'][11],0)
        self.assertEqual(payload['shifts'][0]['start'],16)
        self.assertEqual(json.loads(self.db.execute('SELECT payload FROM wfm_revisions WHERE revision=2 AND published=0').fetchone()['payload'])['demand'][11],7)

    def test_approved_shift_change_can_cross_midnight(self):
        published=copy.deepcopy(self.plan);published['operation']='publish'
        self.call(data=published)
        agent=dict(id=1,role_name='Telefonista')
        request=self.call('POST',actor=agent,action='requests',params={},data={
            'request_type':'CAMBIO_TURNO','requested_date':'2026-09-08',
            'requested_start':44,'requested_end':60,'reason':'Cobertura nocturna',
        })
        self.call('POST',action='requests',params={},data={
            'operation':'decide','request_id':request['request_id'],'decision':'APROBAR',
        })
        payload=json.loads(self.db.execute('SELECT payload FROM wfm_revisions WHERE revision=2').fetchone()['payload'])
        self.assertEqual(payload['shifts'][0]['segments'],[{'start':44,'end':60}])

    def test_request_tracks_source_resolution_and_can_be_cancelled(self):
        published=copy.deepcopy(self.plan);published['operation']='publish'
        self.call(data=published)
        agent=dict(id=1,role_name='Telefonista',display_name='Agente de prueba')
        request=self.call('POST',actor=agent,action='requests',params={},data={
            'request_type':'AUSENCIA','requested_date':'2026-09-08','reason':'Consulta médica',
        })
        self.assertEqual(request['source_revision'],1)
        self.assertEqual(request['source_shift']['start'],16)
        cancelled=self.call('POST',actor=agent,action='requests',params={},data={
            'operation':'cancel','request_id':request['request_id'],
        })
        self.assertEqual(cancelled['status'],'CANCELADA')
        with self.assertRaises(wfm.WfmError) as error:
            self.call('POST',action='requests',params={},data={
                'operation':'decide','request_id':request['request_id'],'decision':'APROBAR',
            })
        self.assertEqual(error.exception.status,409)

    def test_duplicate_pending_request_for_same_day_is_rejected(self):
        published=copy.deepcopy(self.plan);published['operation']='publish'
        self.call(data=published)
        agent=dict(id=1,role_name='Telefonista',display_name='Agente de prueba')
        body={'request_type':'AUSENCIA','requested_date':'2026-09-08','reason':'Consulta médica'}
        self.call('POST',actor=agent,action='requests',params={},data=body)
        with self.assertRaises(wfm.WfmError) as error:
            self.call('POST',actor=agent,action='requests',params={},data=body)
        self.assertEqual(error.exception.status,409)

    def test_republished_schedule_requires_explicit_review_before_approval(self):
        published=copy.deepcopy(self.plan);published['operation']='publish'
        self.call(data=published)
        agent=dict(id=1,role_name='Telefonista',display_name='Agente de prueba')
        request=self.call('POST',actor=agent,action='requests',params={},data={
            'request_type':'AUSENCIA','requested_date':'2026-09-08','reason':'Consulta médica',
        })
        changed=copy.deepcopy(self.plan)
        changed.update(revision=1,operation='publish')
        changed['shifts'][0]['start']=18
        self.call(data=changed)
        decision={'operation':'decide','request_id':request['request_id'],'decision':'APROBAR'}
        with self.assertRaises(wfm.WfmError) as error:
            self.call('POST',action='requests',params={},data=decision)
        self.assertEqual(error.exception.status,409)
        decision['confirm_current_revision']=True
        result=self.call('POST',action='requests',params={},data=decision)
        self.assertEqual(result['applied_revision'],3)

    def test_supervisor_can_create_and_read_own_request(self):
        plan={'revision':0,'demand':[0]*72,'shifts':[{'user_id':2,'start':16}]}
        self.call('POST',params={'date':'2026-09-08','team':'Supervisor'},data={**plan,'operation':'publish'})
        request=self.call('POST',actor=self.actor,action='requests',params={},data={
            'request_type':'CAMBIO_TURNO','requested_date':'2026-09-08',
            'requested_start':18,'requested_end':31,'reason':'Cambio personal',
        })
        own=self.call('GET',actor=self.actor,action='requests',params={'scope':'mine'})
        self.assertEqual([item['request_id'] for item in own],[request['request_id']])

    def test_legacy_schedule_is_visible_until_wfm_supersedes_its_day(self):
        self.db.execute(
            'INSERT INTO work_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (9,1,'2026-09-08','2026-09-07','Telefonista','Noche','22:00','06:00','Guardia histórica','Supervisor','2026-09-01','2026-09-01'),
        )
        legacy=self.call('GET',action='published',params={'week':'2026-09-07','q':'histórica'})
        self.assertEqual((len(legacy),legacy[0]['source'],legacy[0]['end_slot']), (1,'legacy',60))
        published=copy.deepcopy(self.plan);published['operation']='publish'
        self.call(data=published)
        visible=self.call('GET',action='published',params={'week':'2026-09-07','employee_id':'1'})
        self.assertEqual([(row['source'],row['start_slot']) for row in visible],[('wfm',16)])

    def test_stale_write_conflict(self):
        self.call()
        with self.assertRaises(wfm.WfmError) as err:self.call()
        self.assertEqual(err.exception.status,409)

    def test_week_publish_rejects_revision_changed_after_preview(self):
        for offset in range(7):
            plan_date=f'2026-09-{7+offset:02d}'
            self.call('POST',params={'date':plan_date,'team':'Telefonista'},data=copy.deepcopy(self.plan))
        self.call('POST',params={'date':'2026-09-08','team':'Telefonista'},data={**copy.deepcopy(self.plan),'revision':1,'operation':'save'})
        with self.assertRaises(wfm.WfmError) as error:
            self.call('POST',action='publish-week',params={'week':'2026-09-07','team':'Telefonista'},data={
                'confirm_exceptions':True,
                'expected_revisions':{f'2026-09-{7+offset:02d}':1 for offset in range(7)},
            })
        self.assertEqual(error.exception.status,409)

    def test_overlapping_exception_and_duplicate_exception_id_are_rejected(self):
        plan=copy.deepcopy(self.plan)
        plan['shifts'][0]['exceptions']=[
            {'id':'same','type':'Reunión','start':18,'end':20,'note':''},
            {'id':'same','type':'Licencia','start':22,'end':24,'note':''},
        ]
        with self.assertRaises(wfm.WfmError):
            self.call(data=plan)
        plan['shifts'][0]['exceptions'][1]['id']='other'
        plan['shifts'][0]['exceptions'][1]['start']=19
        plan['shifts'][0]['exceptions'][1]['end']=21
        with self.assertRaises(wfm.WfmError):
            self.call(data=plan)

    def test_invalid_inputs(self):
        for change in ({'end':61},{'break':15},{'start':16.5},{'user_id':2},{'locked':'false'}):
            plan=copy.deepcopy(self.plan);plan['shifts'][0].update(change)
            with self.assertRaises(wfm.WfmError):self.call(data=plan)
        self.plan['shifts']*=2
        with self.assertRaises(wfm.WfmError):self.call()

    def test_exception_requires_confirmation(self):
        self.plan['shifts'][0]['break']=18
        self.plan['operation']='publish'
        with self.assertRaises(wfm.WfmError):self.call()
        self.plan['confirm_exceptions']=True
        self.assertEqual(self.call()['published_revision'],1)

    def test_unknown_not_zero(self):
        plan=wfm.validate(self.plan,{1});plan['demand'][0]=None
        self.assertIsNone(wfm.coverage(plan)[0]['difference'])
        with self.assertRaises(wfm.WfmError):wfm.optimize(plan)

    def test_optimizer_moves_to_surplus_and_preserves_locks(self):
        plan=wfm.validate(self.plan,{1});plan['demand'][22]=1
        improved=wfm.optimize(plan)
        self.assertNotEqual(improved['shifts'][0]['break'],22)
        self.assertEqual(wfm.coverage(improved)[22]['difference'],0)
        plan['shifts'][0]['locked']=True
        self.assertEqual(wfm.optimize(plan)['shifts'][0]['break'],22)

    def test_exception_must_be_fully_contained_in_segment_to_prevent_split_and_edit_orphans(self):
        plan=copy.deepcopy(self.plan)
        plan['shifts'][0]['exceptions']=[{'id':'1','type':'Reunión','start':15,'end':17,'note':''}]
        with self.assertRaises(wfm.WfmError):
            self.call(data=plan)
        plan['shifts'][0]['exceptions']=[{'id':'2','type':'Reunión','start':28,'end':30,'note':''}]
        with self.assertRaises(wfm.WfmError):
            self.call(data=plan)
        plan['shifts'][0]['segments']=[{'start':16,'end':20},{'start':22,'end':29}]
        plan['shifts'][0]['exceptions']=[{'id':'3','type':'Reunión','start':19,'end':23,'note':''}]
        with self.assertRaises(wfm.WfmError):
            self.call(data=plan)

if __name__=='__main__':unittest.main()
