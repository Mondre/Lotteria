import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_sources.connector import ArchiveSource, SecureRedirect
from data_sources.importer import import_content, import_file, read_records
from database.store import Store
from games.rules import RuleRegistry


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.sqlite3", RuleRegistry())
        self.record = {"game": "Lotto", "variant": "ordinario", "draw_id": "demo-1",
                       "occurred_at": "2025-01-01T20:00:00+01:00", "wheel": "Roma",
                       "numbers": [1, 2, 3, 4, 5], "extras": {}}

    def test_json_partial_import_and_repeatability(self):
        content = json.dumps([self.record, dict(self.record, numbers=[1, 1, 2, 3, 4])]).encode()
        report = import_content(self.store, content, "json", "test", synthetic=True)
        self.assertEqual((report.inserted, report.rejected), (1, 1))
        self.assertIn("Riga 2", report.errors[0])
        report = import_content(self.store, content, "json", "test", synthetic=True)
        self.assertEqual((report.inserted, report.duplicates, report.rejected), (0, 1, 1))
        self.assertEqual(self.store.count(), 0)
        self.assertTrue(any(row["level"] == "WARNING" for row in self.store.recent_logs()))

    def test_csv_semicolon_and_bom(self):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(self.record), delimiter=";")
        writer.writeheader()
        writer.writerow(dict(self.record, numbers="1 2 3 4 5", extras="{}"))
        path = Path(self.temp.name) / "demo.csv"
        path.write_text(stream.getvalue(), encoding="utf-8-sig")
        self.assertEqual(import_file(self.store, path, True).inserted, 1)

    def test_json_wrong_types(self):
        bad = [None, dict(self.record, draw_id=1), dict(self.record, numbers=[True, 2, 3, 4, 5]),
               dict(self.record, occurred_at="2025-01-01"), dict(self.record, extras=[])]
        report = import_content(self.store, json.dumps(bad).encode(), "json", "test")
        # An empty extras list must not be normalized into a valid object.
        self.assertEqual(report.rejected, len(bad))

    def test_malformed_archive_leaves_database_empty(self):
        for content, format in ((b"{}", "json"), (b"[", "json"), (b"wrong,headers\n1,2", "csv")):
            with self.subTest(format=format), self.assertRaises(ValueError):
                import_content(self.store, content, format, "test")
        self.assertEqual(self.store.count(), 0)

    def test_excel_import(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(list(self.record))
        sheet.append(list(dict(self.record, numbers="1 2 3 4 5", extras="{}").values()))
        path = Path(self.temp.name) / "demo.xlsx"
        workbook.save(path)
        workbook.close()
        self.assertEqual(import_file(self.store, path, True).inserted, 1)

    def test_connector_requires_https_and_supported_format(self):
        for url in ("http://example.com/data", "https://user:password@example.com/data", "not-url"):
            with self.assertRaises(ValueError):
                ArchiveSource(url, "json")
        with self.assertRaises(ValueError):
            ArchiveSource("https://example.com/data", "html")
        with self.assertRaises(ValueError):
            SecureRedirect().redirect_request(None, None, 302, "", {}, "http://example.com")

    def test_connector_imports_response_and_logs_failure_without_url(self):
        response = io.BytesIO(json.dumps([self.record]).encode())
        with patch("data_sources.connector.build_opener") as opener:
            opener.return_value.open.return_value = response
            report = ArchiveSource("https://example.com/archive?private=hidden", "json").update(self.store)
        self.assertEqual(report.inserted, 1)
        with patch("data_sources.connector.build_opener") as opener:
            opener.return_value.open.side_effect = OSError("unavailable")
            with self.assertRaises(RuntimeError):
                ArchiveSource("https://example.com/archive?private=hidden", "json").update(self.store)
        self.assertNotIn("hidden", str([dict(row) for row in self.store.recent_logs()]))

    def test_size_limit(self):
        with patch("data_sources.importer.MAX_BYTES", 5):
            with self.assertRaises(ValueError):
                read_records(b"[1,2,3]", "json")

    def test_marked_synthetic_cannot_enter_real_archive(self):
        content = json.dumps([dict(self.record, synthetic=True)]).encode()
        report = import_content(self.store, content, "json", "test", synthetic=False)
        self.assertEqual(report.rejected, 1)
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(import_content(self.store, content, "json", "test", synthetic=True).inserted, 1)


if __name__ == "__main__":
    unittest.main()
