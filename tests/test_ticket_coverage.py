from datetime import datetime, timedelta, timezone
from itertools import combinations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtesting.tickets import ticket_walk_forward
from games.models import Draw
from games.rules import RuleRegistry
from predictions.engine import generate


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.rules=RuleRegistry()
        start=datetime(2025,1,1,tzinfo=timezone.utc)
        self.draws=[Draw('Lotto','ordinario',str(i),start+timedelta(days=i),(1,2,3,4,5),'Roma',synthetic=True) for i in range(60)]

    def test_disjoint_keeps_count_and_removes_overlap_without_changing_default(self):
        ordinary=generate(self.draws,self.rules,combinations=5,seed=42)
        self.assertEqual(ordinary,generate(self.draws,self.rules,combinations=5,seed=42,ticket_strategy='weighted'))
        diverse=generate(self.draws,self.rules,combinations=5,seed=42,ticket_strategy='disjoint')
        self.assertEqual(len(diverse['tickets']),5)
        self.assertEqual(diverse['tickets'][0],ordinary['tickets'][0])
        self.assertEqual(diverse['coverage']['distinct_numbers'],25)
        self.assertEqual(diverse['coverage']['repeated_slots'],0)
        self.assertNotEqual(diverse['model_version'],ordinary['model_version'])
        self.assertEqual(diverse['training_sha256'],ordinary['training_sha256'])
        self.assertEqual(diverse,generate(self.draws,self.rules,combinations=5,seed=42,ticket_strategy='disjoint'))
        self.assertTrue(all(len(ticket['numbers'])==5 for ticket in diverse['tickets']))
        with self.assertRaisesRegex(ValueError,'18'):
            generate(self.draws,self.rules,combinations=19,ticket_strategy='disjoint')

    def test_exact_coverage_probability_matches_complete_enumeration(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rules.json'
            path.write_text(json.dumps({'schema_version':1,'rules':[{'game':'Test','variant':'base','minimum':1,'maximum':10,'count':2,'wheels':[],'extras':{},'verified':False}]}))
            rules=RuleRegistry(path)
            draw=Draw('Test','base','1',datetime(2025,1,1,tzinfo=timezone.utc),(1,2),synthetic=True)
            result=generate([draw],rules,combinations=3,ticket_strategy='disjoint')
            covered=set(n for ticket in result['tickets'] for n in ticket['numbers'])
            possibilities=list(combinations(range(1,11),2))
            exact=sum(bool(set(actual)&covered) for actual in possibilities)/len(possibilities)
            self.assertAlmostEqual(result['coverage']['theoretical_any_number_under_uniform'],exact)
            all_numbers=generate([draw],rules,combinations=5,ticket_strategy='disjoint')
            self.assertEqual(all_numbers['coverage']['distinct_numbers'],10)
            self.assertEqual(all_numbers['coverage']['theoretical_any_number_under_uniform'],1)

    def test_backtest_baseline_has_same_coverage_and_future_cannot_leak(self):
        result=ticket_walk_forward(self.draws,self.rules,targets=10,combinations=5,initial=30,ticket_strategy='disjoint')
        self.assertEqual(result['model_summary']['mean_distinct_numbers'],25)
        self.assertEqual(result['random_summary']['mean_distinct_numbers'],25)
        self.assertEqual(result['ticket_strategy'],'disjoint')
        from dataclasses import replace
        changed=[*self.draws[:-1],replace(self.draws[-1],numbers=(86,87,88,89,90))]
        other=ticket_walk_forward(changed,self.rules,targets=10,combinations=5,initial=30,ticket_strategy='disjoint')
        self.assertEqual(result['steps'][:-1],other['steps'][:-1])
        self.assertEqual([t['numbers'] for t in result['steps'][-1]['model']],[t['numbers'] for t in other['steps'][-1]['model']])

    def test_api_rejects_impossible_coverage_before_source_access(self):
        from database.store import Store
        from fastapi.testclient import TestClient
        from web.app import create_app
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'RENDER':'','LOTTOPREDICT_WEB_USERNAME':'','LOTTOPREDICT_WEB_PASSWORD':''}):
            store=Store(Path(folder)/'test.sqlite3',self.rules)
            with TestClient(create_app(store,allowed_hosts=['testserver'])) as client,patch('data_sources.sync.Synchronizer.ensure') as ensure:
                for body in ({'operation':'generate','combinations':19}, {'operation':'analyze'}, {'operation':'backtest','evaluation_mode':'single'}):
                    response=client.post('/api/jobs',headers={'X-LottoPredict-Request':'1'},json={**body,'ticket_strategy':'disjoint'})
                    self.assertEqual(response.status_code,422,response.text)
                ensure.assert_not_called()
