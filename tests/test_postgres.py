"""Integrazione reale; solo con un database PostgreSQL di TEST dedicato."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("LOTTOPREDICT_TEST_DATABASE_URL") and importlib.util.find_spec("psycopg"),
                     "PostgreSQL di test non configurato")
class PostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        from database.postgres import PostgresStore
        from games.rules import RuleRegistry
        self.base = os.environ["LOTTOPREDICT_TEST_DATABASE_URL"]
        self.schema = "test_" + uuid.uuid4().hex
        with psycopg.connect(self.base) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.dsn = make_conninfo(self.base, options="-c search_path=" + self.schema)
        self.rules = RuleRegistry()
        self.store = PostgresStore(self.dsn, self.rules)
        self.addCleanup(self.store.close)

    def drop_schema(self):
        import psycopg
        from psycopg import sql
        with psycopg.connect(self.base) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def draw(self, identifier="test-1"):
        from games.models import Draw
        return Draw("Lotto", "ordinario", identifier, datetime(2025, 1, 1, tzinfo=timezone.utc),
                    (1, 2, 3, 4, 5), "Roma", synthetic=True)

    def test_football_tables_prediction_immutability_and_migration(self):
        from football.data import demo
        from football.repository import FootballStore
        from football.engine import backtest
        import psycopg
        from database.postgres import PostgresStore
        repo = FootballStore(self.store)
        self.assertEqual(repo.upsert(demo(), True)["inserted"], 172)
        matches = repo.matches(True)
        prediction = repo.predict(matches[-1].id, True)
        self.assertAlmostEqual(sum(prediction["probabilities"].values()), 1)
        with self.store.connect() as connection:
            with self.assertRaises(psycopg.errors.RaiseException):
                connection.execute("DELETE FROM football_predictions WHERE id=?", (prediction["id"],))
        from dataclasses import replace
        from football.models import instant
        target = matches[-1]
        final = replace(target, status="FINISHED", home_goals=1, away_goals=1,
                        available_at=(instant(target.kickoff) + timedelta(hours=3)).isoformat())
        later = instant(final.available_at) + timedelta(hours=1)
        with patch("football.models.utc_now", return_value=later), patch("football.repository.utc_now", return_value=later):
            repo.upsert([final.payload()], True)
        self.assertEqual(repo.predictions(True)[0]["evaluation"]["outcome"], "X")
        report = repo.save_report(backtest(matches, 5), True)
        self.assertEqual(repo.reports(True)[0]["id"], report["id"])
        with self.store.connect() as connection:
            connection.execute("UPDATE schema_version SET version=3")
        self.store.close()
        self.store = PostgresStore(self.dsn, self.rules)
        self.addCleanup(self.store.close)
        self.assertEqual(len(FootballStore(self.store).matches(True)), 172)
        self.assertEqual(len(FootballStore(self.store).predictions(True)), 1)
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT version FROM schema_version").fetchone()["version"], 4)

    def test_prospective_pair_and_evaluation_on_postgres(self):
        from predictions.prospective import register_trial, list_trials
        from games.models import Draw
        from zoneinfo import ZoneInfo
        now = datetime.now(timezone.utc)
        history = [Draw('Lotto','ordinario',str(i),now-timedelta(days=40-i),(1,2,3,4,5),'Roma',synthetic=True) for i in range(30)]
        day = now.astimezone(ZoneInfo('Europe/Rome')).date() + timedelta(days=2)
        first = register_trial(self.store, history, day, ticket_strategy='disjoint')
        again = register_trial(self.store, history, day, ticket_strategy='disjoint')
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(len(self.store.prediction_history()), 2)
        target = Draw('Lotto','ordinario','lotto:'+day.isoformat(),datetime.combine(day,datetime.min.time(),ZoneInfo('Europe/Rome')),(1,2,3,4,5),'Roma',synthetic=True,date_precision='date')
        with patch('games.rules.datetime', wraps=datetime) as clock:
            clock.now.return_value = target.occurred_at + timedelta(days=1)
            self.store.add_draw(target)
        result = list_trials(self.store,'Roma',True)
        self.assertEqual(result['summaries'][0]['evaluated'],1)
        self.assertEqual(result['trials'][0]['status'],'evaluated')
        self.assertEqual(result['trials'][0]['model']['payload']['coverage']['distinct_numbers'],25)

    def test_winforlife_full_prediction_keeps_numerone_result(self):
        from winforlife.demo import records
        from data_sources.importer import parse_record
        from predictions.engine import generate, save_prediction
        from games.models import Draw
        draws = [parse_record(record,'demo',True) for record in records(80)]
        payload = generate(draws,self.rules,include_numerone=True)
        target = datetime.now(timezone.utc)+timedelta(hours=2)
        identifier = save_prediction(self.store,payload,'wfl-future',target)
        first = payload['tickets'][0]
        actual = Draw('Win for Life','classico','wfl-future',target,tuple(first['numbers']),extras=first['extras'],synthetic=True)
        with patch('games.rules.datetime',wraps=datetime) as clock:
            clock.now.return_value = target+timedelta(hours=1)
            self.store.add_draw(actual)
        saved = self.store.prediction_history()[0]
        self.assertEqual(json.loads(saved['matches'])[0],10)
        self.assertTrue(saved['numerone_matches'][0])
        with self.store.connect() as connection:
            raw = json.loads(connection.execute('SELECT matches FROM prediction_results WHERE prediction_id=?',(identifier,)).fetchone()['matches'])
            self.assertTrue(raw['numerone_matches'][0])
            self.assertEqual(raw['main_matches'][0],10)

    def test_persistence_duplicates_filters_and_restart(self):
        from database.postgres import PostgresStore
        self.assertTrue(self.store.add_draw(self.draw()))
        self.assertFalse(self.store.add_draw(self.draw()))
        self.assertEqual(self.store.count(True), 1)
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(len(self.store.list_draws(synthetic=True)), 1)
        self.assertEqual(self.store.list_draws("MillionDAY", True), [])
        self.store.close()
        self.store = PostgresStore(self.dsn, self.rules)
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.history("Lotto", "ordinario", "Roma", True)[0].numbers, (1, 2, 3, 4, 5))

    def test_concurrent_duplicate_and_bound_parameters(self):
        draw = self.draw("Robert'); DROP TABLE draws;--")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.store.add_draw, [draw, draw]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.store.count(True), 1)

    def test_demo_batch_repeat_and_statistics(self):
        from data_sources.importer import import_file
        from lotto_statistics.engine import analyze
        root = Path(__file__).parent.parent
        report = import_file(self.store, root / "examples/synthetic_lotto_roma.json", True)
        self.assertEqual(report.inserted, 1000)
        self.assertEqual(import_file(self.store, root / "examples/synthetic_lotto_roma.json", True).duplicates, 1000)
        result = analyze(self.store.history("Lotto", "ordinario", "Roma", True), self.rules)
        self.assertEqual(result["draws"], 1000)
        self.assertEqual(self.store.count(), 0)
        from data_sources.preview import preview_content
        preview = preview_content(self.store, (root / "examples/synthetic_lotto_roma.json").read_bytes(), "json", True)
        self.assertEqual(preview["duplicates"], 1000)
        self.assertEqual(preview["new"], 0)

    def test_immutable_forecast_and_result_arrival(self):
        import psycopg
        from games.models import Draw
        from predictions.engine import generate, save_prediction
        payload = generate([self.draw()], self.rules, combinations=2)
        target = datetime.now(timezone.utc) + timedelta(days=1)
        identifier = save_prediction(self.store, payload, "future", target)
        with self.assertRaises(psycopg.errors.RaiseException), self.store.connect() as connection:
            connection.execute("UPDATE predictions SET target_id='changed' WHERE id=?", (identifier,))
        with self.assertRaises(psycopg.errors.RaiseException), self.store.connect() as connection:
            connection.execute("DELETE FROM predictions WHERE id=?", (identifier,))
        draw = Draw("Lotto", "ordinario", "future", target, tuple(payload["tickets"][0]["numbers"]), "Roma", synthetic=True)
        with patch("games.rules.datetime") as clock:
            clock.now.return_value = target + timedelta(hours=1)
            self.store.add_draw(draw)
        self.assertEqual(json.loads(self.store.prediction_history()[0]["matches"])[0], 5)
        with self.assertRaises(psycopg.errors.RaiseException), self.store.connect() as connection:
            connection.execute("DELETE FROM prediction_results WHERE prediction_id=?", (identifier,))

    def test_failed_batch_rolls_back(self):
        with self.assertRaises(RuntimeError), self.store.batch():
            self.store.add_draw(self.draw())
            raise RuntimeError("Interruzione di test")
        self.assertEqual(self.store.count(True), 0)

    def test_v2_migration_and_persistent_source_cache(self):
        from database.postgres import PostgresStore
        self.store.add_draw(self.draw())
        with self.store.connect() as connection:
            connection.execute("ALTER TABLE draws DROP COLUMN date_precision")
            connection.execute("DROP TABLE source_updates")
            connection.execute("DROP TABLE experiments")
            connection.execute("UPDATE schema_version SET version=2")
        self.store.close()
        self.store = PostgresStore(self.dsn, self.rules)
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.count(True), 1)
        self.assertEqual(self.store.history("Lotto", "ordinario", "Roma", True)[0].date_precision, "instant")
        self.store.save_sync_info("test", {"covered_days": ["2025-01-01"], "requested": 1000})
        self.store.close()
        self.store = PostgresStore(self.dsn, self.rules)
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.sync_info("test")["requested"], 1000)
        self.assertEqual(self.store.list_experiments()["total"], 0)

    def test_scientific_result_persistence_and_filter_on_postgres(self):
        from database.postgres import PostgresStore
        created = datetime.now(timezone.utc).isoformat()
        self.store.save_experiment("pg-result", "backtest", "completed", {"seed": 42}, created,
                                   result={"test_steps": 300, "summary": [{"mean_matches": .25}]})
        self.store.close()
        self.store = PostgresStore(self.dsn, self.rules)
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.experiment("pg-result")["result"]["test_steps"], 300)
        self.assertEqual(self.store.list_experiments(operation="backtest")["total"], 1)
        self.assertEqual(self.store.list_experiments(operation="generate")["total"], 0)

    def test_automatic_update_and_verified_history_on_postgres(self):
        from tests.test_automatic_sources import fixture_archive
        from data_sources.lotto_official import parse_archive
        from data_sources.sync import Synchronizer
        draws, metadata = parse_archive(fixture_archive(), self.rules)
        synchronizer = Synchronizer(self.store, lambda *_: (draws, metadata))
        result = synchronizer.ensure("Lotto", "ordinario", "Roma")
        self.assertEqual(result["inserted"], 22)
        self.assertEqual(len(synchronizer.history("Lotto", "ordinario", "Roma", 1000)), 2)
        self.assertEqual(synchronizer.ensure("Lotto", "ordinario", "Roma")["state"], "cached")


if __name__ == "__main__":
    unittest.main()
