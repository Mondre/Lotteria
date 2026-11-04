import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from data_sources.importer import import_content
from data_sources.preview import preview_content
from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "preview.sqlite3", RuleRegistry())
        self.row = {"game": "Lotto", "variant": "ordinario", "wheel": "Roma", "draw_id": "a",
                    "occurred_at": "2025-01-01T20:00:00+01:00", "numbers": [1, 2, 3, 4, 5], "extras": {}}

    def test_preview_is_read_only_and_predicts_import_classification(self):
        self.store.add_draw(Draw("Lotto", "ordinario", "existing", datetime(2025, 1, 1, 19, tzinfo=timezone.utc),
                                 (1, 2, 3, 4, 5), "Roma", synthetic=True))
        records = [self.row, self.row, dict(self.row, draw_id="existing"),
                   dict(self.row, numbers=[2, 3, 4, 5, 6]), dict(self.row, numbers=[1, 1, 2, 3, 4])]
        content = json.dumps(records).encode()
        logs = len(self.store.recent_logs())
        result = preview_content(self.store, content, "json", True)
        self.assertEqual((result["new"], result["duplicates"], result["conflicts"], result["invalid"]), (1, 2, 1, 1))
        self.assertEqual(self.store.count(True), 1)
        self.assertEqual(len(self.store.recent_logs()), logs)
        imported = import_content(self.store, content, "json", "test", True)
        self.assertEqual((imported.inserted, imported.duplicates, imported.rejected), (1, 2, 2))

    def test_real_and_synthetic_lookups_never_mix(self):
        draw = Draw("Lotto", "ordinario", "a", datetime(2025, 1, 1, 19, tzinfo=timezone.utc),
                    (1, 2, 3, 4, 5), "Roma", synthetic=True)
        self.store.add_draw(draw)
        found = self.store.existing_draws([draw, replace(draw, synthetic=False)])
        self.assertIn((draw.game, draw.variant, draw.wheel, draw.draw_id, True), found)
        self.assertEqual(len(found), 1)
        self.assertEqual(preview_content(self.store, json.dumps([self.row]).encode(), "json")["new"], 1)

    def test_empty_and_invalid_headers_rejected(self):
        for content, format in ((b"[]", "json"), (b"game,numbers\nLotto,1", "csv")):
            with self.assertRaises(ValueError):
                preview_content(self.store, content, format)

    def test_lookup_batches_more_than_sqlite_parameter_limit(self):
        draws = [Draw("Lotto", "ordinario", str(i), datetime(2025, 1, 1, tzinfo=timezone.utc),
                      (1, 2, 3, 4, 5), "Roma", synthetic=True) for i in range(450)]
        with self.store.batch():
            for draw in draws:
                self.store.add_draw(draw)
        self.assertEqual(len(self.store.existing_draws(draws)), 450)

    def test_samples_and_errors_are_bounded(self):
        content = json.dumps([dict(self.row, numbers=[0, 1, 2, 3, 4]) for _ in range(120)]).encode()
        result = preview_content(self.store, content, "json")
        self.assertEqual(result["invalid"], 120)
        self.assertEqual(len(result["sample"]), 20)
        self.assertEqual(len(result["errors"]), 100)

    def test_ambiguous_fields_rejected(self):
        for content, format in ((b'[{"game":"Lotto","game":"MillionDAY"}]', "json"),
                                (b'game,game,variant,draw_id,occurred_at,numbers\nLotto,Lotto,ordinario,a,x,y', "csv")):
            with self.assertRaises(ValueError):
                preview_content(self.store, content, format)
