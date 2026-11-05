from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry
from predictions.prospective import list_trials, register_trial, validate_day


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'test.sqlite3',RuleRegistry())
        now=datetime.now(timezone.utc)
        self.history=[Draw('Lotto','ordinario',str(i),now-timedelta(days=40-i),(1,2,3,4,5),'Roma',synthetic=True) for i in range(30)]
        self.day=now.astimezone(ZoneInfo('Europe/Rome')).date()+timedelta(days=2)

    def test_atomic_pair_is_persistent_idempotent_and_immutable(self):
        result=register_trial(self.store,self.history,self.day,ticket_strategy='disjoint')
        self.assertEqual(result['status'],'awaiting_result')
        self.assertTrue(result['registered_before_day'])
        self.assertEqual(result['model']['payload']['training_sha256'],result['random']['payload']['training_sha256'])
        for arm in ('model','random'):
            self.assertEqual(len({n for t in result[arm]['payload']['tickets'] for n in t['numbers']}),25)
        again=register_trial(self.store,self.history,self.day,ticket_strategy='disjoint')
        self.assertEqual(result['id'],again['id']);self.assertTrue(again['already_registered'])
        self.assertEqual(len(self.store.prediction_history()),2)
        reopened=Store(self.store.path,self.store.rules)
        self.assertEqual(list_trials(reopened,'Roma',True)['trials'][0]['id'],result['id'])
        with self.store.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('DELETE FROM predictions WHERE id=?',(result['model']['id'],))

    def test_second_failure_rolls_back_both_arms(self):
        from predictions.engine import save_prediction
        calls=[]
        def fail_second(*args):
            calls.append(1)
            if len(calls)==2:raise ValueError('Errore artificiale')
            return save_prediction(*args)
        with patch('predictions.prospective.save_prediction',side_effect=fail_second),self.assertRaises(ValueError):
            register_trial(self.store,self.history,self.day)
        self.assertEqual(self.store.prediction_history(),[])

    def test_evaluation_arrives_later_and_protocols_are_not_mixed(self):
        first=register_trial(self.store,self.history,self.day)
        register_trial(self.store,self.history,self.day,seed=99)
        draw=Draw('Lotto','ordinario','lotto:'+self.day.isoformat(),datetime.combine(self.day,datetime.min.time(),ZoneInfo('Europe/Rome')),
                  (1,2,3,4,5),'Roma',synthetic=True,date_precision='date')
        later=draw.occurred_at+timedelta(days=1)
        with patch('games.rules.datetime',wraps=datetime) as clock:
            clock.now.return_value=later
            self.store.add_draw(draw)
        data=list_trials(self.store,'Roma',True)
        self.assertEqual(len(data['summaries']),2)
        self.assertTrue(all(s['evaluated']==1 for s in data['summaries']))
        pair=next(p for p in data['trials'] if p['id']==first['id'])
        self.assertEqual(pair['status'],'evaluated')
        self.assertEqual(pair['actual_numbers'],[1,2,3,4,5])
        for arm in ('model','random'):
            expected=[len(set(t['numbers'])&set(draw.numbers)) for t in pair[arm]['payload']['tickets']]
            self.assertEqual(pair[arm]['matches'],expected)
        self.assertEqual(list_trials(self.store,'Bari',True)['trials'],[])
        self.assertEqual(list_trials(self.store,'Roma',False)['trials'],[])

    def test_same_day_or_past_cannot_be_registered(self):
        today=datetime.now(ZoneInfo('Europe/Rome')).date()
        for day in (today,today-timedelta(days=1)):
            with self.assertRaises(ValueError):validate_day(day)
        with self.assertRaises(ValueError):register_trial(self.store,[],self.day)

    def test_different_targets_are_not_declared_comparable(self):
        from predictions.prospective import _pair, _rows
        created = register_trial(self.store,self.history,self.day)
        rows = _rows(self.store,'Roma',True)
        for row in rows:
            if row['payload']['prospective_comparison_v1']['arm'] == 'random':
                row['target_id'] = 'different-target'
        pair = _pair(rows,created['id'])
        self.assertEqual(pair['status'],'not_comparable')

    def test_existing_ordinary_forecasts_are_not_trial_results(self):
        from predictions.engine import generate,save_prediction
        payload=generate(self.history,self.store.rules)
        save_prediction(self.store,payload,'other',datetime.now(timezone.utc)+timedelta(days=3))
        self.assertEqual(list_trials(self.store,'Roma',True)['trials'],[])


class ProspectiveWebTests(unittest.TestCase):
    def test_api_future_checks_and_demo_flow(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        from data_sources.importer import import_file
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'RENDER':'','LOTTOPREDICT_WEB_USERNAME':'','LOTTOPREDICT_WEB_PASSWORD':'','LOTTOPREDICT_OFFICIAL_SYNC_ENABLED':''}):
            store=Store(Path(folder)/'web.sqlite3',RuleRegistry())
            import_file(store,Path(__file__).resolve().parent.parent/'examples/synthetic_lotto_roma.json',True)
            headers={'X-LottoPredict-Request':'1'}
            future=datetime.now(ZoneInfo('Europe/Rome')).date()+timedelta(days=2)
            body={'synthetic':True,'target_day':future.isoformat(),'ticket_strategy':'disjoint'}
            with TestClient(create_app(store,allowed_hosts=['testserver'])) as client:
                self.assertEqual(client.post('/api/prospective-lotto',json=body).status_code,403)
                for bad in ({'target_day':datetime.now(ZoneInfo('Europe/Rome')).date().isoformat()}, {'combinations':19}, {'game':'MillionDAY','wheel':''}):
                    self.assertEqual(client.post('/api/prospective-lotto',headers=headers,json={**body,**bad}).status_code,422)
                response=client.post('/api/prospective-lotto',headers=headers,json=body)
                self.assertEqual(response.status_code,202,response.text)
                for _ in range(1000):
                    result=client.get('/api/jobs/'+response.json()['id']).json()
                    if result['status'] in ('completed','failed'):break
                    time.sleep(.01)
                self.assertEqual(result['status'],'completed',result)
                data=client.get('/api/prospective-lotto?synthetic=true').json()
                self.assertEqual(len(data['trials']),1)
                self.assertEqual(data['summaries'][0]['evaluated'],0)
                self.assertIsNone(data['summaries'][0]['model']['mean_matches'])
                self.assertEqual(client.post('/api/prospective-lotto',headers=headers,json={**body,'synthetic':False}).status_code,409)
