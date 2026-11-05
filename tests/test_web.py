from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"), "Installare requirements-web-test.txt")
class WebTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.environment = patch.dict("os.environ", {"RENDER": "", "LOTTOPREDICT_WEB_USERNAME": "", "LOTTOPREDICT_WEB_PASSWORD": "", "RENDER_EXTERNAL_HOSTNAME": "", "LOTTOPREDICT_OFFICIAL_SYNC_ENABLED": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        from fastapi.testclient import TestClient
        from database.store import Store
        from games.rules import RuleRegistry
        from web.app import create_app
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "web.sqlite3", RuleRegistry())
        self.app = create_app(self.store, allowed_hosts=["testserver"])
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.headers = {"X-LottoPredict-Request": "1"}
        self.sync_patch = patch("data_sources.sync.Synchronizer.ensure", return_value={"state": "stored"})
        self.ensure_mock = self.sync_patch.start()
        self.addCleanup(self.sync_patch.stop)

    def post(self, path, **kwargs):
        return self.client.post(path, headers=self.headers, **kwargs)

    def wait_job(self, response):
        self.assertEqual(response.status_code, 202, response.text)
        key = response.json()["id"]
        for _ in range(1000):
            job = self.client.get("/api/jobs/" + key).json()
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(.01)
        self.fail("Il job non è terminato")

    def demo(self):
        return self.wait_job(self.post("/api/demo"))

    def test_static_health_empty_and_headers(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Dashboard", page.text)
        self.assertIn("frame-ancestors 'none'", page.headers["content-security-policy"])
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard").json()["real_count"], 0)

    def test_origin_and_host_checks(self):
        self.assertEqual(self.client.post("/api/demo").status_code, 403)
        result = self.client.post("/api/demo", headers={**self.headers, "Origin": "https://elsewhere.example"})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.client.get("/api/health", headers={"host": "elsewhere.example"}).status_code, 400)

    def test_demo_idempotent_and_separate_from_real(self):
        self.assertEqual(self.demo()["result"]["inserted"], 1000)
        self.assertEqual(self.demo()["result"]["duplicates"], 1000)
        real = self.client.get("/api/dashboard").json()
        demo = self.client.get("/api/dashboard?synthetic=true").json()
        self.assertEqual(real["selected_count"], 0)
        self.assertEqual(demo["selected_count"], 1000)
        self.assertEqual(real["real_count"], 0)
        self.assertEqual(len(demo["draws"]), 100)

    def test_archive_pages_cover_selection_without_changing_statistics(self):
        self.demo()
        url = "/api/dashboard?synthetic=true"
        first = self.client.get(url).json()
        seen = []
        previous_date = None
        for offset in range(0, 1000, 100):
            page = self.client.get(url + f"&archive_offset={offset}").json()
            self.assertEqual(page["archive_page"], {"offset": offset, "limit": 100, "total": 1000})
            self.assertEqual(page["latest"], first["latest"])
            self.assertEqual(page["frequency"], first["frequency"])
            for draw in page["draws"]:
                date = datetime.fromisoformat(draw["occurred_at"])
                if previous_date is not None:
                    self.assertLess(date, previous_date)
                previous_date = date
                seen.append(draw["draw_id"])
        self.assertEqual(len(set(seen)), 1000)
        # Stale offsets are clamped when the window or dataset changes.
        short = self.client.get(url + "&limit=125&archive_offset=900").json()
        self.assertEqual(short["archive_page"], {"offset": 100, "limit": 100, "total": 125})
        self.assertEqual(len(short["draws"]), 25)
        real = self.client.get("/api/dashboard?archive_offset=900").json()
        self.assertEqual(real["archive_page"], {"offset": 0, "limit": 100, "total": 0})
        self.assertEqual(real["draws"], [])
        other_wheel = self.client.get(url + "&wheel=Milano&archive_offset=100").json()
        self.assertEqual(other_wheel["draws"], [])
        for offset in ("-1", "10001", "oops"):
            self.assertEqual(self.client.get(url + "&archive_offset=" + offset).status_code, 422)

    def test_import_analyze_and_reopen_extra_results(self):
        records = [{"game": "Win for Life", "variant": "classico", "draw_id": f"extra-{i}",
                    "occurred_at": f"2025-01-0{i + 1}T12:00:00+01:00", "numbers": list(range(1, 11)),
                    "extras": {"numerone": value}, "synthetic": True}
                   for i, value in enumerate((1, 1, 20))]
        content = json.dumps(records)
        preview = self.wait_job(self.post("/api/import/preview?format=json&synthetic=true", content=content))
        self.assertEqual(self.store.count(True), 0)
        imported = self.wait_job(self.post("/api/import?format=json&synthetic=true", content=content))
        self.assertEqual(imported["result"]["inserted"], 3)
        self.assertEqual(preview["status"], "completed")
        selection = {"game": "Win for Life", "variant": "classico", "wheel": "", "synthetic": True}
        job = self.wait_job(self.post("/api/jobs", json={**selection, "operation": "analyze"}))
        self.assertEqual(job["status"], "completed", job)
        extra = job["result"]["extras_analysis"]["numerone"]
        self.assertEqual(extra["frequencies"][0]["count"], 2)
        self.assertEqual(self.store.experiment(job["id"])["result"]["extras_analysis"]["numerone"], extra)
        exported = self.client.get("/api/archive/export", params=selection).json()
        self.assertEqual(sorted(row["extras"]["numerone"] for row in exported), [1, 1, 20])
        main_only = self.wait_job(self.post("/api/jobs", json={**selection, "operation": "generate", "combinations": 2}))
        self.assertEqual(main_only["status"], "completed", main_only)
        self.assertTrue(all("extras" not in ticket for ticket in main_only["result"]["tickets"]))

    def test_upload_and_errors(self):
        row = {"game": "Lotto", "variant": "ordinario", "wheel": "Roma", "draw_id": "<script>1</script>",
               "occurred_at": "2025-01-01T20:00:00+01:00", "numbers": [1, 2, 3, 4, 5], "synthetic": True}
        content = json.dumps([row])
        blocked = self.wait_job(self.post("/api/import?format=json", content=content))
        self.assertEqual(blocked["result"]["rejected"], 1)
        ok = self.wait_job(self.post("/api/import?format=json&synthetic=true", content=content))
        self.assertEqual(ok["result"]["inserted"], 1)
        failed = self.wait_job(self.post("/api/import?format=json", content=b"invalid json"))
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.post("/api/import?format=html", content=b"x").status_code, 422)
        self.assertEqual(self.post("/api/import?format=json", content=b"").status_code, 422)
        from unittest.mock import patch
        with patch("data_sources.importer.MAX_BYTES", 3):
            self.assertEqual(self.post("/api/import?format=json", content=b"1234").status_code, 413)

    def test_scientific_end_to_end_and_immutable_save(self):
        self.demo()
        body = {"game": "Lotto", "variant": "ordinario", "wheel": "Roma", "synthetic": True}
        for operation in ("analyze", "generate", "backtest", "simulate"):
            job = self.wait_job(self.post("/api/jobs", json={**body, "operation": operation}))
            self.assertEqual(job["status"], "completed", job)
            if operation == "generate":
                generated = job
            if operation == "backtest":
                self.assertEqual(job["result"]["test_steps"], 300)
                self.assertIn("Nessun algoritmo", job["result"]["conclusion"])
        date = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        saved = self.post("/api/predictions", json={"job_id": generated["id"], "target_id": "future-1", "target_date": date})
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(len(self.client.get("/api/predictions").json()), 1)
        self.assertEqual(self.client.patch("/api/predictions", headers=self.headers).status_code, 405)
        self.assertEqual(self.post("/api/predictions", json={"job_id": generated["id"], "target_id": "past", "target_date": "2025-01-01T00:00:00Z"}).status_code, 422)

    def test_selection_validation_and_missing_jobs(self):
        self.assertEqual(self.client.get("/api/dashboard?wheel=wrong").status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard?limit=10001").status_code, 422)
        self.assertEqual(self.client.get("/api/jobs/unknown").status_code, 404)
        self.assertEqual(self.post("/api/jobs", json={"operation": "generate", "model": "unknown"}).status_code, 422)
        job = self.wait_job(self.post("/api/jobs", json={"operation": "generate"}))
        self.assertEqual(job["status"], "failed")
        self.assertIn("Nessuna estrazione", job["error"])

    def test_preview_confirm_hash_and_archive_export_round_trip(self):
        row = {"game": "Lotto", "variant": "ordinario", "wheel": "Roma", "draw_id": "preview",
               "occurred_at": "2025-01-01T20:00:00+01:00", "numbers": [1, 2, 3, 4, 5], "extras": {}, "synthetic": True}
        content = json.dumps([row]).encode()
        preview = self.wait_job(self.post("/api/import/preview?format=json&synthetic=true", content=content))
        self.assertEqual(preview["result"]["new"], 1)
        self.assertEqual(self.store.count(True), 0)
        sha = preview["result"]["sha256"]
        mismatch = self.post("/api/import?format=json&synthetic=true&expected_sha256=" + sha, content=b"[]")
        self.assertEqual(mismatch.status_code, 409)
        imported = self.wait_job(self.post("/api/import?format=json&synthetic=true&expected_sha256=" + sha, content=content))
        self.assertEqual(imported["result"]["inserted"], 1)
        exported = self.client.get("/api/archive/export?synthetic=true")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()[0]["draw_id"], "preview")
        self.assertTrue(exported.json()[0]["synthetic"])
        self.assertIn("attachment", exported.headers["content-disposition"])
        self.assertEqual(self.client.get("/api/archive/export?synthetic=false").json(), [])

    def test_manual_entry_valid_duplicate_conflict_and_date_validation(self):
        row = {"game": "Lotto", "variant": "ordinario", "wheel": "Roma", "draw_id": "manual",
               "occurred_at": "2025-01-01T20:00:00+01:00", "numbers": [1, 2, 3, 4, 5], "extras": {}, "synthetic": True,
               "source": "Documento sintetico di test"}
        self.assertTrue(self.post("/api/draws", json=row).json()["inserted"])
        self.assertTrue(self.post("/api/draws", json=row).json()["duplicate"])
        for changed in (dict(row, numbers=[2, 3, 4, 5, 6]), dict(row, numbers=[True, 2, 3, 4, 5]),
                        dict(row, occurred_at="2025-01-01T20:00:00"), dict(row, source=" "),
                        dict(row, occurred_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat())):
            self.assertEqual(self.post("/api/draws", json=changed).status_code, 422)
        self.assertEqual(self.store.count(True), 1)
        self.assertEqual(self.client.get("/api/import/template").status_code, 200)

    def test_job_queue_is_bounded(self):
        from threading import Event
        from fastapi import HTTPException
        event = Event()
        jobs = self.app.state.jobs
        try:
            for _ in range(4):
                jobs.submit("test", lambda: event.wait(10))
            with self.assertRaises(HTTPException) as failure:
                jobs.submit("test", lambda: True)
            self.assertEqual(failure.exception.status_code, 429)
        finally:
            event.set()

    def test_basic_auth_protects_pages_static_and_api_but_not_health(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from web.app import create_app
        credentials = ("test-user", "test-password-only-123")
        with patch.dict("os.environ", {"LOTTOPREDICT_WEB_USERNAME": credentials[0], "LOTTOPREDICT_WEB_PASSWORD": credentials[1],
                                        "RENDER": "true", "RENDER_EXTERNAL_HOSTNAME": "example.onrender.com"}):
            app = create_app(self.store, allowed_hosts=["testserver"])
        with TestClient(app) as client:
            for path in ("/", "/static/app.js", "/api/config", "/api/predictions", "/api/logs", "/api/experiments"):
                self.assertEqual(client.get(path).status_code, 401)
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/config", auth=credentials).status_code, 200)
            self.assertEqual(client.get("/", auth=("wrong", credentials[1])).status_code, 401)
            self.assertEqual(client.get("/", headers={"Authorization": "Basic invalid"}).status_code, 401)
            self.assertEqual(client.get("/", auth=credentials, headers={"host": "example.onrender.com"}).status_code, 200)
            self.assertEqual(client.post("/api/demo", headers=self.headers).status_code, 401)

    def test_render_requires_credentials(self):
        from unittest.mock import patch
        from web.app import create_app
        with patch.dict("os.environ", {"RENDER": "true", "LOTTOPREDICT_WEB_USERNAME": "", "LOTTOPREDICT_WEB_PASSWORD": ""}):
            with self.assertRaisesRegex(ValueError, "USERNAME"):
                create_app(self.store)

    def test_real_analysis_updates_first_and_reuses_persistent_cache(self):
        from tests.test_automatic_sources import fixture_archive
        from data_sources.lotto_official import parse_archive
        from unittest.mock import Mock
        self.sync_patch.stop()
        draws, metadata = parse_archive(fixture_archive(), self.store.rules)
        fetcher = Mock(return_value=(draws, metadata))
        self.app.state.synchronizer.fetcher = fetcher
        self.app.state.synchronizer.enabled = True
        first = self.wait_job(self.post("/api/jobs", json={"operation": "analyze"}))
        self.assertEqual(first["status"], "completed", first)
        self.assertEqual(first["result"]["draws"], 2)
        self.assertEqual(first["result"]["data_update"]["state"], "updated")
        self.assertEqual(self.store.count(), 22)
        second = self.wait_job(self.post("/api/jobs", json={"operation": "generate"}))
        self.assertEqual(second["result"]["data_update"]["state"], "cached")
        self.assertEqual(fetcher.call_count, 1)
        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual(dashboard["latest"]["date_precision"], "date")
        forced = self.wait_job(self.post("/api/sources/sync", json={}))
        self.assertEqual(forced["status"], "completed")
        self.assertEqual(fetcher.call_count, 2)

    def test_synthetic_and_stored_modes_do_not_download(self):
        self.demo()
        result = self.wait_job(self.post("/api/jobs", json={"operation": "analyze", "synthetic": True}))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.ensure_mock.call_count, 0)
        self.wait_job(self.post("/api/jobs", json={"operation": "generate", "auto_update": False}))
        self.assertEqual(self.ensure_mock.call_count, 0)
        self.assertEqual(self.post("/api/sources/sync", json={"synthetic": True}).status_code, 422)

    def test_saved_generation_can_be_opened_and_used_after_restart(self):
        from fastapi.testclient import TestClient
        from database.store import Store
        from games.rules import RuleRegistry
        from web.app import create_app
        self.demo()
        generated = self.wait_job(self.post("/api/jobs", json={"operation": "generate", "synthetic": True}))
        self.assertTrue(generated["persisted"])
        reopened_store = Store(self.store.path, RuleRegistry())
        with TestClient(create_app(reopened_store, allowed_hosts=["testserver"])) as client:
            result = client.get("/api/jobs/" + generated["id"]).json()
            self.assertEqual(result["result"], generated["result"])
            self.assertEqual(result["request"]["seed"], 42)
            listing = client.get("/api/experiments?operation=generate").json()
            self.assertEqual(listing["total"], 1)
            self.assertNotIn("result", listing["items"][0])
            date = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
            saved = client.post("/api/predictions", headers=self.headers,
                                json={"job_id": generated["id"], "target_id": "after-restart", "target_date": date})
            self.assertEqual(saved.status_code, 201)

    def test_failed_calculation_is_stored_but_preview_does_not_create_history(self):
        failed = self.wait_job(self.post("/api/jobs", json={"operation": "generate", "auto_update": False}))
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.client.get("/api/experiments").json()["total"], 1)
        self.assertEqual(self.client.get("/api/experiments?operation=analyze").json()["total"], 0)
        self.assertEqual(self.client.get("/api/experiments?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/experiments?operation=unknown").status_code, 422)

    def test_database_save_failure_is_not_reported_as_persisted_success(self):
        from unittest.mock import patch
        self.demo()
        with patch.object(self.store, "save_experiment", side_effect=OSError("Test database offline")), self.assertLogs(level="ERROR"):
            result = self.wait_job(self.post("/api/jobs", json={"operation": "generate", "synthetic": True}))
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["persisted"])
        self.assertNotIn("result", result)
        self.assertEqual(self.client.get("/api/experiments").json()["total"], 0)

    def test_multimodel_comparison_is_saved_with_one_common_test(self):
        self.demo()
        result = self.wait_job(self.post("/api/jobs", json={"operation": "backtest", "synthetic": True,
                                                          "models": ["temporal"], "initial": 700}))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["result"]["model_names"], ["uniform", "frequency", "temporal"])
        self.assertEqual(result["result"]["test_steps"], 300)
        self.assertTrue(all(len(step["models"]) == 3 for step in result["result"]["steps"]))
        saved = self.store.experiment(result["id"])
        self.assertEqual(saved["request"]["models"], ["temporal"])
        self.assertEqual(saved["result"], result["result"])

    def test_comparison_validation_does_not_download_or_start_jobs(self):
        invalid = [{"operation": "generate", "models": ["temporal"]},
                   {"operation": "backtest", "models": ["temporal", "temporal"]},
                   {"operation": "backtest", "models": ["unknown"]},
                   {"operation": "backtest", "models": ["random_forest"], "initial": 20},
                   {"operation": "backtest", "models": ["ensemble"], "initial": 80},
                   {"operation": "backtest", "models": ["logistic"], "train_window": 20}]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.post("/api/jobs", json=body).status_code, 422)
        self.assertEqual(self.ensure_mock.call_count, 0)
        self.assertEqual(self.store.list_experiments()["total"], 0)

    def test_baselines_only_comparison_is_supported(self):
        self.demo()
        result = self.wait_job(self.post("/api/jobs", json={"operation": "backtest", "synthetic": True, "models": []}))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["result"]["model_names"], ["uniform", "frequency"])

    def test_source_progress_is_read_only_and_exposes_no_raw_receipts(self):
        from data_sources.lotto_api import PROGRESS_KEY
        self.assertEqual(self.client.get("/api/sources/status").json(), {"enabled": False, "progress": None})
        self.store.save_sync_info(PROGRESS_KEY, {"state": "failed", "completed": 500, "requested": 1000})
        data = self.client.get("/api/sources/status").json()
        self.assertEqual(data["progress"]["completed"], 500)
        self.assertEqual(data["progress"]["state"], "failed")
        self.assertNotIn("payload", data["progress"])

    def test_official_source_requires_explicit_configuration(self):
        from unittest.mock import Mock
        self.sync_patch.stop()
        self.app.state.synchronizer.fetcher = Mock(side_effect=AssertionError("Nessun download atteso"))
        self.assertFalse(self.client.get("/api/config").json()["official_sync_enabled"])
        self.assertEqual(self.post("/api/sources/sync", json={}).status_code, 409)
        self.wait_job(self.post("/api/jobs", json={"operation": "generate"}))
        self.assertEqual(self.app.state.synchronizer.fetcher.call_count, 0)


if __name__ == "__main__":
    unittest.main()
