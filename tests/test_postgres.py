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


if __name__ == "__main__":
    unittest.main()
