import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rules = RuleRegistry()
        self.store = Store(Path(self.temp.name) / "draws.sqlite3", self.rules)
        self.draw = Draw("Lotto", "ordinario", "test-1", datetime(2025, 1, 1, tzinfo=timezone.utc),
                         (1, 2, 3, 4, 5), "Roma", synthetic=True)

    def test_persistence_and_duplicate(self):
        self.assertTrue(self.store.add_draw(self.draw))
        self.assertFalse(self.store.add_draw(self.draw))
        reopened = Store(self.store.path, self.rules)
        self.assertEqual(reopened.count(True), 1)
        self.assertEqual(reopened.count(), 0)
        self.assertEqual(len(reopened.recent_logs()), 1)

    def test_conflicting_duplicate_never_overwrites(self):
        self.store.add_draw(self.draw)
        with self.assertRaisesRegex(ValueError, "contenuto diverso"):
            self.store.add_draw(replace(self.draw, numbers=(2, 3, 4, 5, 6)))
        self.assertEqual(self.store.list_draws(synthetic=True)[0]["numbers"], "[1, 2, 3, 4, 5]")

    def test_invalid_draws_rejected(self):
        for draw in (replace(self.draw, numbers=(1, 1, 2, 3, 4)),
                     replace(self.draw, numbers=(0, 1, 2, 3, 4)),
                     replace(self.draw, numbers=(True, 2, 3, 4, 5)),
                     replace(self.draw, wheel="inesistente"),
                     replace(self.draw, variant="inesistente"),
                     replace(self.draw, draw_id=""),
                     replace(self.draw, occurred_at=datetime(2025, 1, 1)),
                     replace(self.draw, occurred_at=datetime.now(timezone.utc) + timedelta(days=1))):
            with self.subTest(draw=draw), self.assertRaises(ValueError):
                self.store.add_draw(draw)
        self.assertEqual(self.store.count(True), 0)

    def test_every_configured_variant(self):
        for (game, variant), rule in self.rules.rules.items():
            with self.subTest(game=game, variant=variant):
                numbers = tuple(range(rule["minimum"], rule["minimum"] + rule["count"]))
                extras = {name: (rule["maximum"] if spec["distinct_main"] else spec["minimum"])
                          for name, spec in rule["extras"].items()}
                draw = Draw(game, variant, "same-id", self.draw.occurred_at, numbers,
                            rule["wheels"][0] if rule["wheels"] else "", extras, True)
                self.assertTrue(self.store.add_draw(draw))
        self.assertEqual(self.store.count(True), len(self.rules.rules))

    def test_wheels_and_synthetic_are_separate(self):
        self.store.add_draw(self.draw)
        self.store.add_draw(replace(self.draw, wheel="Milano"))
        self.store.add_draw(replace(self.draw, synthetic=False))
        self.assertEqual(self.store.count(True), 2)
        self.assertEqual(self.store.count(), 1)

    def test_chronological_order_and_filter(self):
        self.store.add_draw(self.draw)
        self.store.add_draw(replace(self.draw, draw_id="older", occurred_at=self.draw.occurred_at - timedelta(days=1)))
        rows = self.store.list_draws("Lotto", synthetic=True, limit=1)
        self.assertEqual(rows[0]["draw_id"], "test-1")
        self.assertEqual(self.store.list_draws("MillionDAY", synthetic=True), [])

    def test_extra_validation(self):
        draw = Draw("Win for Life", "classico", "1", self.draw.occurred_at, tuple(range(1, 11)))
        with self.assertRaises(ValueError):
            self.rules.validate(draw)
        self.rules.validate(replace(draw, extras={"numerone": 5}))
        with self.assertRaises(ValueError):
            self.rules.validate(replace(draw, extras={"numerone": 21}))

    def test_unknown_database_version_is_not_downgraded(self):
        with self.store.connect() as connection:
            connection.execute("PRAGMA user_version = 99")
        with self.assertRaises(ValueError):
            Store(self.store.path, self.rules)


if __name__ == "__main__":
    unittest.main()
