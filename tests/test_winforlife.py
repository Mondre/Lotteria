from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from backtesting.tickets import ticket_walk_forward
from data_sources.importer import import_content,parse_record
from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry
from predictions.engine import generate,save_prediction
from winforlife.demo import records


class WinForLifeTests(unittest.TestCase):
    def setUp(self):
        self.rules=RuleRegistry()
        self.draws=[parse_record(row,'test sintetico',True) for row in records(120)]

    def test_full_ticket_has_separate_numerone_and_preserves_main_rng(self):
        main=generate(self.draws,self.rules,combinations=5,seed=7)
        full=generate(self.draws,self.rules,combinations=5,seed=7,include_numerone=True)
        self.assertEqual([t['numbers'] for t in main['tickets']],[t['numbers'] for t in full['tickets']])
        self.assertNotEqual(main['model_version'],full['model_version'])
        self.assertTrue(all(len(t['numbers'])==10 and len(set(t['numbers']))==10 and 1<=t['extras']['numerone']<=20 for t in full['tickets']))
        self.assertTrue(all('extras' not in t for t in main['tickets']))
        self.assertEqual(full,generate(self.draws,self.rules,combinations=5,seed=7,include_numerone=True))
        biased=[replace(d,numbers=tuple(range(1,11)),extras={'numerone':5}) for d in self.draws]
        first=generate(biased,self.rules,include_numerone=True)['tickets'][0]
        self.assertEqual(first['extras']['numerone'],5)
        self.assertIn(5,first['numbers'])

    def test_flat_column_import_and_conflicts_are_checked(self):
        base=records(1)[0];flat={k:v for k,v in base.items() if k!='extras'};flat['numerone']='5'
        self.assertEqual(parse_record(flat,'test',True).extras,{'numerone':5})
        for extra in ({'numerone':6},{'numerone':True},{'numerone':5.0}):
            with self.assertRaises(ValueError):parse_record({**flat,'extras':extra},'test',True)
        with self.assertRaises(ValueError):self.rules.validate(replace(self.draws[0],extras={'numerone':21}))
        with self.assertRaises(ValueError):self.rules.validate(replace(self.draws[0],extras={}))
        from zoneinfo import ZoneInfo
        day=self.draws[0].occurred_at.astimezone(ZoneInfo('Europe/Rome')).replace(hour=0,minute=0,second=0,microsecond=0)
        with self.assertRaises(ValueError):self.rules.validate(replace(self.draws[0],occurred_at=day,date_precision='date'))

    def test_past_only_numerone_and_joint_counts(self):
        a=ticket_walk_forward(self.draws,self.rules,targets=20,initial=50,include_numerone=True)
        target=self.draws[-1]
        changed=[*self.draws[:-1],replace(target,extras={'numerone':1 if target.extras['numerone']!=1 else 2})]
        b=ticket_walk_forward(changed,self.rules,targets=20,initial=50,include_numerone=True)
        self.assertEqual(a['steps'][:-1],b['steps'][:-1])
        for arm in ('model','random'):
            self.assertEqual([t['extras'] for t in a['steps'][-1][arm]],[t['extras'] for t in b['steps'][-1][arm]])
            summary=a[arm+'_summary']
            self.assertEqual(sum(row['combinations'] for row in summary['joint_distribution']),100)
            self.assertEqual(summary['numerone_hits'],sum(t['numerone_hit'] for row in a['steps'] for t in row[arm]))
        self.assertEqual(a['theoretical_mean_per_combination'],5)

    def test_saved_forecast_persists_main_and_numerone_results(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite3',self.rules)
            result=generate(self.draws,self.rules,include_numerone=True)
            future=datetime.now(timezone.utc)+timedelta(hours=2)
            identifier=save_prediction(store,result,'future-wfl',future)
            actual=Draw('Win for Life','classico','future-wfl',future,tuple(result['tickets'][0]['numbers']),extras={'numerone':result['tickets'][0]['extras']['numerone']},synthetic=True)
            with patch('games.rules.datetime',wraps=datetime) as clock:
                clock.now.return_value=future+timedelta(hours=1)
                store.add_draw(actual)
            saved=store.prediction_history()[0]
            self.assertEqual(json.loads(saved['matches'])[0],10)
            self.assertTrue(saved['numerone_matches'][0])
            self.assertEqual(saved['actual_numerone'],actual.extras['numerone'])
            with store.connect() as connection:
                stored=json.loads(connection.execute('SELECT matches FROM prediction_results WHERE prediction_id=?',(identifier,)).fetchone()['matches'])
                self.assertEqual(stored['main_matches'][0],10)
                with self.assertRaises(sqlite3.IntegrityError):connection.execute('DELETE FROM prediction_results WHERE prediction_id=?',(identifier,))
            self.assertEqual(Store(store.path,self.rules).prediction_history()[0]['winforlife_result'],stored)
            invalid={**result,'tickets':[{**result['tickets'][0],'extras':{'numerone':99}}]}
            with self.assertRaises(ValueError):save_prediction(store,invalid,'another',future)

    def test_demo_is_separate_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'demo.sqlite3',self.rules)
            data=json.dumps(records()).encode()
            self.assertEqual(import_content(store,data,'json','demo',True).inserted,1000)
            self.assertEqual(import_content(store,data,'json','demo',True).duplicates,1000)
            self.assertEqual(store.count(),0)
            self.assertEqual(import_content(store,data,'json','demo',False).rejected,1000)


class WinForLifeWebTests(unittest.TestCase):
    def test_complete_api_flow_and_invalid_scope(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'RENDER':'','LOTTOPREDICT_WEB_USERNAME':'','LOTTOPREDICT_WEB_PASSWORD':'','LOTTOPREDICT_OFFICIAL_SYNC_ENABLED':''}):
            store=Store(Path(folder)/'web.sqlite3',RuleRegistry())
            with TestClient(create_app(store,allowed_hosts=['testserver'])) as client:
                headers={'X-LottoPredict-Request':'1'}
                def wait(response):
                    self.assertEqual(response.status_code,202,response.text)
                    for _ in range(1000):
                        item=client.get('/api/jobs/'+response.json()['id']).json()
                        if item['status'] in ('completed','failed'):return item
                        time.sleep(.01)
                    self.fail('Job non completato')
                self.assertEqual(wait(client.post('/api/winforlife/demo',headers=headers))['result']['inserted'],1000)
                body={'game':'Win for Life','variant':'classico','wheel':'','synthetic':True,'include_numerone':True}
                generated=wait(client.post('/api/jobs',headers=headers,json={**body,'operation':'generate'}))
                self.assertEqual(generated['status'],'completed',generated)
                self.assertTrue(all('numerone' in ticket['extras'] for ticket in generated['result']['tickets']))
                tested=wait(client.post('/api/jobs',headers=headers,json={**body,'operation':'backtest','evaluation_mode':'tickets','test_targets':20,'initial':700}))
                self.assertEqual(tested['status'],'completed',tested)
                self.assertIn('numerone_rate',tested['result']['model_summary'])
                self.assertTrue(store.experiment(tested['id'])['request']['include_numerone'])
                self.assertEqual(client.post('/api/jobs',headers=headers,json={'operation':'generate','include_numerone':True}).status_code,422)
                template=client.get('/api/winforlife/template').text
                self.assertEqual(template.splitlines()[0].split(',')[5],'numerone')
                self.assertNotIn('\\r',template)
