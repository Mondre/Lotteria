from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, BadZipFile

from data_sources.lotto_official import ARCHIVE, PAGE, WHEELS, archive_url, check_url, fetch_archive, parse_archive
from data_sources.sync import KEY, Synchronizer
from database.store import SCHEMA, Store
from games.models import Draw
from games.rules import RuleRegistry


def fixture_archive(days=2):
    """Formato di prova ipotizzato; NON contiene estrazioni reali."""
    codes = [code for code in WHEELS if code != "NZ"]
    rows = [f"{date(2025, 1, 1) + timedelta(days=i):%Y/%m/%d}\t{code}\t1\t2\t3\t4\t5"
            for i in range(days) for code in codes]
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("storico.txt", "\n".join(rows))
    return stream.getvalue()


class AutomaticSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rules = RuleRegistry()
        self.store = Store(Path(self.temp.name) / "auto.sqlite3", self.rules)
        self.draws, self.metadata = parse_archive(fixture_archive(), self.rules)

    def fetcher(self, registry, limit):
        return self.draws, self.metadata

    def test_published_link_discovery_and_redirect_allowlist(self):
        self.assertEqual(archive_url(f'<a href="{ARCHIVE}">Scarica</a>'.encode()), ARCHIVE)
        for content in (b"<p>Collegamento rimosso</p>", b'<a href="https://evil.example/storico01-oggi.zip">Archivio</a>'):
            with self.assertRaises(ValueError):
                archive_url(content)
        for url in ("http://www.brightstarlottery.it/a", "https://www.brightstarlottery.it:8443/a", "https://user:secret@www.lotto-italia.it/a"):
            with self.assertRaises(ValueError):
                check_url(url)

    def test_download_and_parse_with_injected_fixture_not_live_data(self):
        with patch("data_sources.lotto_official.download", side_effect=[f'<a href="{ARCHIVE}">ZIP</a>'.encode(), fixture_archive()]) as download:
            draws, metadata = fetch_archive(self.rules)
        self.assertEqual(len(draws), 22)
        self.assertEqual(download.call_args_list[0].args[0], PAGE)
        self.assertEqual(download.call_args_list[1].args[0], ARCHIVE)
        self.assertEqual(metadata["source_url"], ARCHIVE)
        self.assertTrue(all(draw.date_precision == "date" for draw in draws))
        self.assertEqual(draws[0].occurred_at.hour, 0)
        self.assertEqual(draws[0].occurred_at.utcoffset(), timedelta(hours=1))

    def test_latest_complete_days_only(self):
        draws, metadata = parse_archive(fixture_archive(days=4), self.rules, limit=2)
        self.assertEqual(len(draws), 22)
        self.assertEqual(metadata["available"], 4)
        self.assertEqual(metadata["latest_day"], "2025-01-04")
        self.assertTrue(all(draw.draw_id.startswith("lotto:2025-01-0") for draw in draws))

    def test_corrupt_or_unrecognized_archive_fails_before_writes(self):
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("data.txt", "2025/01/01 BA 1 1 2 3 4")
        for content in (b"not a zip", stream.getvalue()):
            with self.assertRaises((ValueError, BadZipFile)):
                parse_archive(content, self.rules)
        self.assertEqual(self.store.count(), 0)

    def test_atomic_sync_cache_force_and_restart(self):
        sync = Synchronizer(self.store, self.fetcher)
        result = sync.ensure("Lotto", "ordinario", "Roma")
        self.assertEqual(result["inserted"], 22)
        self.assertEqual(self.store.count(), 22)
        self.assertEqual(self.store.count(True), 0)
        reopened = Store(self.store.path, self.rules)
        cached = Synchronizer(reopened, lambda *_: self.fail("Cache non riutilizzata")).ensure("Lotto", "ordinario", "Roma")
        self.assertEqual(cached["state"], "cached")
        forced = sync.ensure("Lotto", "ordinario", "Roma", force=True)
        self.assertEqual(forced["inserted"], 0)
        self.assertEqual(forced["duplicates"], 22)

    def test_automatic_history_excludes_manual_copies_of_same_event(self):
        sync = Synchronizer(self.store, self.fetcher)
        sync.ensure("Lotto", "ordinario", "Roma")
        manual = replace(next(draw for draw in self.draws if draw.wheel == "Roma"), draw_id="manual-copy", source="test")
        self.store.add_draw(manual)
        self.assertEqual(len(self.store.history("Lotto", "ordinario", "Roma")), 3)
        self.assertEqual(len(sync.history("Lotto", "ordinario", "Roma", 1000)), 2)

    def test_conflict_never_overwrites_numbers_or_success_state(self):
        sync = Synchronizer(self.store, self.fetcher)
        before = sync.ensure("Lotto", "ordinario", "Roma")
        changed = [replace(self.draws[0], numbers=(6, 7, 8, 9, 10)), *self.draws[1:]]
        other = Synchronizer(self.store, lambda *_: (changed, self.metadata))
        with self.assertRaises(ValueError):
            other.ensure("Lotto", "ordinario", "Roma", force=True)
        self.assertEqual(self.store.sync_info(KEY), before)
        self.assertEqual(self.store.count(), 22)

    def test_failed_fetch_never_falls_back_to_demo_or_claims_success(self):
        def failure(*_):
            raise OSError("Errore di rete di test")
        with self.assertRaises(ValueError):
            Synchronizer(self.store, failure).ensure("Lotto", "ordinario", "Roma")
        self.assertIsNone(self.store.sync_info(KEY))
        self.assertEqual(self.store.count(True), 0)

    def test_sqlite_v2_migration_preserves_existing_data(self):
        path = Path(self.temp.name) / "v2.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.executescript(SCHEMA.replace("    date_precision TEXT NOT NULL DEFAULT 'instant',\n", ""))
            connection.execute("DROP TABLE source_updates")
            connection.execute("PRAGMA user_version=2")
            connection.execute("INSERT INTO draws VALUES(1,'Lotto','ordinario','Roma','old','2025-01-01T00:00:00+00:00','[1,2,3,4,5]','{}',0,'test','2025-01-02T00:00:00+00:00')")
        migrated = Store(path, self.rules)
        self.assertEqual(migrated.count(), 1)
        self.assertEqual(migrated.history("Lotto", "ordinario", "Roma")[0].date_precision, "instant")
        self.assertIsNone(migrated.sync_info(KEY))

    def test_date_only_results_do_not_score_forecasts_issued_same_day(self):
        draw = self.draws[11]  # Secondo giorno della fixture, mezzanotte italiana.
        day = draw.occurred_at
        payload = json.dumps({"train_end": (day - timedelta(days=2)).isoformat(), "tickets": [{"numbers": draw.numbers}]})
        with self.store.connect() as connection:
            for identifier, created in (("previous-day", day - timedelta(hours=12)), ("same-day", day + timedelta(hours=9))):
                connection.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?)",
                                   (identifier, created.isoformat(), draw.game, draw.variant, draw.wheel, False,
                                    draw.draw_id, (day + timedelta(hours=20)).isoformat(), payload))
        self.store.add_draw(draw)
        results = {row["id"]: row["matches"] for row in self.store.prediction_history()}
        self.assertEqual(json.loads(results["previous-day"]), [5])
        self.assertIsNone(results["same-day"])
        statuses = {row["id"]: row["evaluation_status"] for row in self.store.prediction_history()}
        self.assertEqual(statuses["previous-day"], "evaluated")
        self.assertEqual(statuses["same-day"], "unscorable_time")
