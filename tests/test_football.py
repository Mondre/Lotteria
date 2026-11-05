from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from database.store import Store
from football.data import demo, fetch_season, read_upload
from football.engine import backtest, forecast, training
from football.models import Match, instant
from football.repository import FootballStore
from games.rules import RuleRegistry


class FootballTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'football.sqlite3', RuleRegistry())
        self.repo = FootballStore(self.store)
        self.records = demo()

    def seed(self):
        self.repo.upsert(self.records, True)
        return self.repo.matches(True)

    def test_demo_separate_persistent_and_idempotent(self):
        self.assertEqual(self.repo.upsert(self.records, True)['inserted'], 172)
        self.assertEqual(self.repo.upsert(self.records, True)['duplicates'], 172)
        self.assertEqual(len(FootballStore(Store(self.store.path, RuleRegistry())).matches(True)), 172)
        self.assertEqual(self.repo.matches(False), [])
        self.assertEqual(self.store.count(True), 0)
        with self.assertRaises(ValueError):
            self.repo.upsert(self.records, False)

    def test_atomic_import_and_final_conflict(self):
        bad = [self.records[0], dict(self.records[1], id=self.records[0]['id'])]
        with self.assertRaises(ValueError):
            self.repo.upsert(bad, True)
        self.assertEqual(self.repo.matches(True), [])
        self.seed()
        changed = dict(self.records[0], home_goals=19)
        with self.assertRaises(ValueError):
            self.repo.upsert([changed], True)
        self.assertNotEqual(self.repo.matches(True)[0].home_goals, 19)

    def test_validation_rejects_ambiguous_times_unknown_scores_and_same_teams(self):
        for changes in ({'kickoff': '2025-01-01T12:00:00'}, {'home_goals': True}, {'available_at': None},
                        {'away': self.records[0]['home']}, {'status': 'SCHEDULED'}, {'season': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Match.parse(dict(self.records[0], **changes), True)

    def test_probabilities_sum_to_one_and_training_excludes_unavailable_results(self):
        matches = self.seed()
        target = matches[-1]
        cutoff = datetime.now(timezone.utc)
        result = forecast(matches, target, cutoff)
        self.assertAlmostEqual(sum(result['probabilities'].values()), 1)
        self.assertTrue(all(0 < p < 1 for p in result['probabilities'].values()))
        unavailable = replace(matches[0], available_at=(cutoff + timedelta(days=1)).isoformat())
        history = training([unavailable, *matches[1:]], cutoff)
        self.assertNotIn(unavailable, history)
        self.assertEqual(len(history), 167)
        self.assertNotEqual(forecast([unavailable, *matches[1:]], target, cutoff)['training_sha256'], result['training_sha256'])

    def test_future_outcomes_and_simultaneous_results_do_not_leak(self):
        matches = self.seed()
        result = backtest(matches, 20)
        last = next(m for m in matches if m.id == result['steps'][-1]['id'])
        changed = [replace(m, home_goals=19) if m.id == last.id else m for m in matches]
        other = backtest(changed, 20)
        self.assertEqual(result['steps'][:-1], other['steps'][:-1])
        self.assertEqual(result['steps'][-1]['probabilities'], other['steps'][-1]['probabilities'])
        coincident = replace(matches[1], kickoff=matches[0].kickoff)
        self.assertNotIn(coincident, training([matches[0], coincident], instant(coincident.kickoff)))
        self.assertEqual(result['targets'], 20)

    def test_saved_forecast_is_immutable_and_evaluates_after_result(self):
        matches = self.seed()
        target = matches[-1]
        prediction = self.repo.predict(target.id, True)
        with self.store.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('DELETE FROM football_predictions WHERE id=?', (prediction['id'],))
        final = replace(target, status='FINISHED', home_goals=2, away_goals=1,
                        available_at=(instant(target.kickoff) + timedelta(hours=3)).isoformat())
        later = instant(final.available_at) + timedelta(hours=1)
        with patch('football.models.utc_now', return_value=later), patch('football.repository.utc_now', return_value=later):
            self.repo.upsert([final.payload()], True)
        saved = self.repo.predictions(True)[0]
        self.assertEqual(saved['evaluation']['outcome'], '1')
        self.assertEqual(saved['training_sha256'], prediction['training_sha256'])
        self.assertGreaterEqual(saved['evaluation']['brier'], 0)
        self.assertEqual(saved['target']['status'], 'SCHEDULED')
        with self.assertRaises(ValueError):
            self.repo.predict(target.id, True)

    def test_no_training_fails_and_csv_roundtrip_has_strict_boolean(self):
        self.repo.upsert([self.records[-1]], True)
        with self.assertRaisesRegex(ValueError, '30'):
            self.repo.predict(self.records[-1]['id'], True)
        content = b'id,season,kickoff,home,away,status,synthetic\n1,2025,2027-01-01T12:00:00+00:00,A,B,SCHEDULED,true\n'
        self.assertTrue(read_upload(content, 'csv', True)[0]['synthetic'])
        with self.assertRaises(ValueError):
            read_upload(content.replace(b'true', b'yes'), 'csv', True)

    def test_disabled_source_does_not_make_network_requests(self):
        with patch.dict('os.environ', {'FOOTBALL_DATA_ENABLED': '', 'FOOTBALL_DATA_API_TOKEN': ''}), patch('football.data.build_opener') as opener:
            with self.assertRaises(ValueError):
                fetch_season(2025)
            opener.assert_not_called()

    def test_provider_adapter_accepts_only_serie_a_and_preserves_fixture_identity(self):
        from unittest.mock import MagicMock
        target = self.records[-1]
        payload = {"competition": {"code": "SA"}, "matches": [{"id": 123,
                   "utcDate": target["kickoff"], "season": {"startDate": "2026-08-01"},
                   "status": "TIMED", "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}}]}
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict('os.environ', {'FOOTBALL_DATA_ENABLED': 'true', 'FOOTBALL_DATA_API_TOKEN': 'fixture-token'}), patch('football.data.build_opener', return_value=opener):
            records = fetch_season(2026)
            self.assertEqual(records[0]['id'], 'fd:123')
            self.assertFalse(records[0]['synthetic'])
            self.assertEqual(records[0]['status'], 'SCHEDULED')
            Match.parse(records[0], False)
            payload['competition']['code'] = 'OTHER'
            response.read.return_value = json.dumps(payload).encode()
            with self.assertRaises(ValueError):
                fetch_season(2026)

    def test_provider_denies_redirects_and_sanitizes_errors(self):
        from football.data import NoRedirect
        from urllib.error import HTTPError
        from unittest.mock import Mock
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://other.example/')
        opener = Mock()
        opener.open.side_effect = HTTPError('https://api.football-data.org', 401, 'fixture-token', {}, None)
        with patch.dict('os.environ', {'FOOTBALL_DATA_ENABLED': 'true', 'FOOTBALL_DATA_API_TOKEN': 'fixture-token'}), patch('football.data.build_opener', return_value=opener):
            with self.assertRaises(ValueError) as error:
                fetch_season(2026)
            self.assertNotIn('fixture-token', str(error.exception))

    def test_v3_migration_preserves_lottery_data(self):
        from games.models import Draw
        self.store.add_draw(Draw('Lotto', 'ordinario', 'preserved', datetime(2025,1,1,tzinfo=timezone.utc), (1,2,3,4,5), 'Roma', synthetic=True))
        with self.store.connect() as connection:
            for name in ('football_evaluations','football_predictions','football_reports','football_matches'):
                connection.execute('DROP TABLE '+name)
            connection.execute('PRAGMA user_version=3')
        migrated = Store(self.store.path, self.store.rules)
        self.assertEqual(migrated.count(True), 1)
        with migrated.connect() as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM football_matches').fetchone()[0], 0)


class FootballWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        self.env = patch.dict('os.environ', {'RENDER': '', 'LOTTOPREDICT_WEB_USERNAME': '', 'LOTTOPREDICT_WEB_PASSWORD': '', 'FOOTBALL_DATA_ENABLED': '', 'FOOTBALL_DATA_API_TOKEN': ''})
        self.env.start(); self.addCleanup(self.env.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'web.sqlite3', RuleRegistry())
        self.client = TestClient(create_app(self.store, allowed_hosts=['testserver']))
        self.client.__enter__(); self.addCleanup(self.client.__exit__, None, None, None)
        self.headers = {'X-LottoPredict-Request': '1'}

    def job(self, url):
        response = self.client.post(url, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        for _ in range(1000):
            result = self.client.get('/api/jobs/' + response.json()['id']).json()
            if result['status'] in ('completed', 'failed'):
                return result
            time.sleep(.01)
        self.fail('Job non completato')

    def test_demo_forecast_backtest_export_and_existing_lottery(self):
        self.assertEqual(self.client.get('/football').status_code, 200)
        self.assertEqual(self.client.post('/api/football/demo').status_code, 403)
        self.assertEqual(self.client.get('/api/football').json()['total'], 0)
        self.assertEqual(self.job('/api/football/demo')['status'], 'completed')
        data = self.client.get('/api/football?synthetic=true').json()
        self.assertEqual(data['total'], 172)
        target = data['fixtures'][0]
        prediction = self.client.post('/api/football/predictions', json={'match_id': target['id'], 'synthetic': True}, headers=self.headers)
        self.assertEqual(prediction.status_code, 201, prediction.text)
        result = self.job('/api/football/backtest?synthetic=true')
        self.assertEqual(result['status'], 'completed', result)
        exported = self.client.get('/api/football/export?synthetic=true').json()
        self.assertEqual(len(exported['predictions']), 1)
        self.assertEqual(len(exported['reports']), 1)
        self.assertEqual(len(exported['matches']), 172)
        self.assertEqual(self.client.get('/api/dashboard').json()['real_count'], 0)
        self.assertEqual(self.client.post('/api/football/sync?season=2025', headers=self.headers).status_code, 409)
        self.assertIn('available_at', self.client.get('/api/football/template').text)
