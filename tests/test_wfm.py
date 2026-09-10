"""Pruebas WFM aisladas: nunca abre centro_operativo.db."""
import copy
import json
import sqlite3
import unittest
from app import wfm


class WfmTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript(wfm.SCHEMA + '''
        CREATE TABLE roles(id INTEGER,name TEXT);
        CREATE TABLE users(id INTEGER,display_name TEXT,role_id INTEGER,active INTEGER);
        INSERT INTO roles VALUES(1,'Telefonista'),(2,'Supervisor'),(3,'Administrador');
        INSERT INTO users VALUES(1,'Agente de prueba',1,1),(2,'Supervisor de prueba',2,1);
        ''')
        self.actor = dict(id=2, role_name='Supervisor')
        self.params = dict(date='2026-09-08', team='Telefonista')
        self.plan = dict(revision=0, demand=[0]*48, shifts=[dict(user_id=1, start=16)])

    def tearDown(self):
        self.db.close()

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

    def test_stale_write_conflict(self):
        self.call()
        with self.assertRaises(wfm.WfmError) as err:self.call()
        self.assertEqual(err.exception.status,409)

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
