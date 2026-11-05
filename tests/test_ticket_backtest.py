from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from backtesting.tickets import ticket_walk_forward
from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry


class TicketTest(unittest.TestCase):
    def setUp(self):
        self.rules = RuleRegistry()
        rng = np.random.default_rng(18)
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.draws = [Draw('Lotto','ordinario',str(i),start+timedelta(days=i),tuple(sorted((rng.choice(90,5,replace=False)+1).tolist())),'Roma',synthetic=True) for i in range(60)]

    def test_all_tickets_counted_and_target_never_in_training(self):
        from predictions.engine import generate
        seen = []
        def spy(history, registry, name, combinations, seed):
            seen.append([d.draw_id for d in history])
            return generate(history,registry,name,combinations,seed)
        result = ticket_walk_forward(self.draws,self.rules,targets=10,combinations=5,initial=30,generator=spy)
        self.assertEqual(len(seen),20)
        for index,history in enumerate(seen):
            self.assertEqual(history,[str(i) for i in range(50+index//2)])
        for label in ('model_summary','random_summary'):
            self.assertEqual(sum(result[label]['combination_distribution']),50)
            self.assertEqual(sum(result[label]['best_per_draw_distribution']),10)
            self.assertEqual(result[label]['total_combinations'],50)
        for row in result['steps']:
            for label in ('model','random'):
                self.assertEqual(len({tuple(t['numbers']) for t in row[label]}),5)
                for ticket in row[label]:
                    self.assertEqual(ticket['matched_numbers'],sorted(set(ticket['numbers']) & set(row['actual_numbers'])))
                    self.assertEqual(ticket['matches'],len(ticket['matched_numbers']))
        self.assertAlmostEqual(result['theoretical_mean_per_combination'],25/90)

    def test_future_changes_do_not_change_previous_predictions(self):
        first = ticket_walk_forward(self.draws,self.rules,targets=10,initial=30)
        changed = [*self.draws[:-1],replace(self.draws[-1],numbers=(1,2,3,4,5))]
        other = ticket_walk_forward(changed,self.rules,targets=10,initial=30)
        self.assertEqual(first['steps'][:-1],other['steps'][:-1])
        for label in ('model','random'):
            self.assertEqual([t['numbers'] for t in first['steps'][-1][label]],[t['numbers'] for t in other['steps'][-1][label]])
        self.assertEqual(first['steps'][-1]['training_sha256'],other['steps'][-1]['training_sha256'])

    def test_grouped_thresholds_count_each_draw_once(self):
        def fixed(history,registry,model,count,seed):
            return {'tickets':[{'numbers':[1,2,3,4,5]},{'numbers':[1,2,3,4,6]}], 'training_sha256':'test','rules_sha256':'test'}
        draws = [replace(d,numbers=(1,2,7,8,9)) for d in self.draws]
        result = ticket_walk_forward(draws,self.rules,targets=10,combinations=2,initial=30,generator=fixed)
        threshold = result['model_summary']['thresholds'][1]
        self.assertEqual(threshold['combinations'],20)
        self.assertEqual(threshold['draws'],10)
        self.assertEqual(threshold['draw_rate'],1)
        self.assertEqual(result['model_summary']['thresholds'][2]['draws'],0)

    def test_window_seed_reproducibility_and_validation(self):
        a=ticket_walk_forward(self.draws,self.rules,targets=5,initial=30,train_window=20,seed=7)
        self.assertEqual(a,ticket_walk_forward(self.draws,self.rules,targets=5,initial=30,train_window=20,seed=7))
        self.assertTrue(all(row['train_size']==20 for row in a['steps']))
        for params in ({'targets':100,'initial':30},{'targets':200,'combinations':100}, {'targets':2,'model':'logistic','initial':20}):
            with self.assertRaises(ValueError):
                ticket_walk_forward(self.draws,self.rules,**params)
        with self.assertRaises(ValueError):
            ticket_walk_forward([*self.draws[:-1],replace(self.draws[-1],occurred_at=self.draws[-2].occurred_at)],self.rules,targets=5,initial=30)


class TicketWebTest(unittest.TestCase):
    def test_persistent_report_and_validation_before_network(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        from data_sources.importer import import_file
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'RENDER':'','LOTTOPREDICT_WEB_USERNAME':'','LOTTOPREDICT_WEB_PASSWORD':'','LOTTOPREDICT_OFFICIAL_SYNC_ENABLED':''}):
            store=Store(Path(folder)/'test.sqlite3',RuleRegistry())
            import_file(store,Path(__file__).resolve().parent.parent/'examples/synthetic_lotto_roma.json',True)
            headers={'X-LottoPredict-Request':'1'}
            with TestClient(create_app(store,allowed_hosts=['testserver'])) as client:
                body={'operation':'backtest','evaluation_mode':'tickets','test_targets':20,'synthetic':True,'initial':700,'combinations':5}
                response=client.post('/api/jobs',json=body,headers=headers)
                self.assertEqual(response.status_code,202,response.text)
                key=response.json()['id']
                for _ in range(1000):
                    job=client.get('/api/jobs/'+key).json()
                    if job['status'] in ('completed','failed'):break
                    time.sleep(.01)
                self.assertEqual(job['status'],'completed',job)
                self.assertEqual(job['result']['model_summary']['total_combinations'],100)
                self.assertEqual(store.experiment(key)['result'],job['result'])
                self.assertEqual(store.experiment(key)['request']['evaluation_mode'],'tickets')
                for bad in ({'operation':'generate'}, {'models':['temporal']}, {'test_targets':200,'combinations':100}, {'limit':500}):
                    invalid=client.post('/api/jobs',json={**body,**bad},headers=headers)
                    self.assertEqual(invalid.status_code,422,invalid.text)
                self.assertEqual(store.prediction_history(),[])
