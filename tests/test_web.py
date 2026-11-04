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
        self.environment = patch.dict("os.environ", {"RENDER": "", "LOTTOPREDICT_WEB_USERNAME": "", "LOTTOPREDICT_WEB_PASSWORD": "", "RENDER_EXTERNAL_HOSTNAME": ""})
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
            for path in ("/", "/static/app.js", "/api/config", "/api/predictions", "/api/logs"):
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


if __name__ == "__main__":
    unittest.main()
