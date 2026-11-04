from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time
import importlib.util
import unittest

from database.store import Store
from games.rules import RuleRegistry


class ExperimentStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "experiments.sqlite3"
        self.store = Store(self.path, RuleRegistry())
        self.created = datetime.now(timezone.utc).isoformat()

    def test_result_request_and_errors_survive_restart_and_are_paginated(self):
        self.store.save_experiment("first", "backtest", "completed", {"seed": 17, "model": "frequency"}, self.created,
                                   result={"summary": [{"mean_matches": .25}], "test_steps": 300})
        self.store.save_experiment("second", "generate", "failed", {"seed": 18}, self.created, error="Storico insufficiente")
        reopened = Store(self.path, RuleRegistry())
        self.assertEqual(reopened.experiment("first")["request"]["seed"], 17)
        self.assertEqual(reopened.experiment("first")["result"]["test_steps"], 300)
        self.assertEqual(reopened.experiment("second")["status"], "failed")
        self.assertEqual(reopened.list_experiments(limit=1)["total"], 2)
        self.assertEqual(len(reopened.list_experiments(limit=1, offset=1)["items"]), 1)
        filtered = reopened.list_experiments(operation="backtest")
        self.assertEqual(filtered["total"], 1)
        self.assertNotIn("result", filtered["items"][0])
        self.assertIsNone(reopened.experiment("missing"))

    def test_invalid_state_and_non_finite_result_are_not_saved(self):
        with self.assertRaises(ValueError):
            self.store.save_experiment("invalid", "preview", "completed", {}, self.created, result={})
        with self.assertRaises(ValueError):
            self.store.save_experiment("nan", "analyze", "completed", {}, self.created, result={"value": float("nan")})
        self.assertEqual(self.store.list_experiments()["total"], 0)

    def wait(self, jobs, identifier):
        for _ in range(500):
            item = jobs.get(identifier)
            if item["status"] in ("completed", "failed"):
                return item
            time.sleep(.01)
        self.fail("Job non completato")

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "Dipendenze web non installate")
    def test_job_restored_without_rerunning_calculation(self):
        from web.jobs import Jobs
        calls = []
        def calculate():
            calls.append(1)
            return {"values": [1, 2, 3]}
        jobs = Jobs(self.store)
        self.addCleanup(jobs.pool.shutdown, wait=True)
        identifier = jobs.submit("analyze", calculate, {"seed": 42})["id"]
        result = self.wait(jobs, identifier)
        self.assertTrue(result["persisted"])
        reopened = Jobs(Store(self.path, RuleRegistry()))
        self.addCleanup(reopened.pool.shutdown, wait=True)
        self.assertEqual(reopened.get(identifier)["result"], {"values": [1, 2, 3]})
        self.assertEqual(calls, [1])

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "Dipendenze web non installate")
    def test_preview_is_not_persisted(self):
        from web.jobs import Jobs
        jobs = Jobs(self.store)
        self.addCleanup(jobs.pool.shutdown, wait=True)
        key = jobs.submit("preview", lambda: {"total": 1})["id"]
        self.assertEqual(self.wait(jobs, key)["status"], "completed")
        self.assertEqual(self.store.list_experiments()["total"], 0)
