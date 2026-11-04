import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.stats import hypergeom

from backtesting.engine import null_tail, walk_forward
from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry
from lotto_statistics.engine import matrix
from machine_learning.models import ExperimentalModel, features
from predictions.engine import generate, save_prediction


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        config = {"schema_version": 1, "rules": [{"game": "Test", "variant": "base", "minimum": 1,
                  "maximum": 6, "count": 2, "wheels": [], "extras": {}, "verified": False}]}
        path = root / "rules.json"
        path.write_text(json.dumps(config))
        self.rules = RuleRegistry(path)
        self.store = Store(root / "test.sqlite3", self.rules)
        rng = np.random.default_rng(3)
        self.draws = [Draw("Test", "base", str(i), datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                           tuple((rng.choice(6, 2, replace=False) + 1).tolist()), synthetic=True) for i in range(120)]

    def test_exact_hypergeometric_null(self):
        expected = hypergeom.sf(0, 6, 2, 2)
        self.assertAlmostEqual(null_tail(1, 1, 6, 2), expected)
        self.assertAlmostEqual(null_tail(0, 10, 6, 2), 1)
        self.assertEqual(null_tail(3, 1, 6, 2), 0)

    def test_walk_forward_passes_only_prefixes_to_model(self):
        values, _ = matrix(self.draws[:12], self.rules)
        seen_fit, seen_score = [], []
        class Spy:
            def __init__(self, name, count, seed):
                self.name = name
            def fit(self, history):
                seen_fit.append(history.copy())
            def score(self, history):
                seen_score.append(history.copy())
                return history.mean(axis=0)
        result = walk_forward(self.draws[:12], self.rules, ("spy",), initial=8, retrain_every=2, model_factory=Spy)
        self.assertEqual(result["test_steps"], 4)
        for index, history in enumerate(seen_score):
            t = 8 + index // 3  # uniform, frequency e spy
            np.testing.assert_array_equal(history, values[:t])
        for index, history in enumerate(seen_fit):
            np.testing.assert_array_equal(history, values[:8 + (index // 3) * 2])

    def test_future_changes_do_not_change_earlier_predictions(self):
        draws = self.draws[:25]
        changed = draws[:-1] + [replace(draws[-1], numbers=(1, 2))]
        a = walk_forward(draws, self.rules, initial=20)
        b = walk_forward(changed, self.rules, initial=20)
        self.assertEqual(a["steps"][:-1], b["steps"][:-1])
        for name in a["steps"][-1]["models"]:
            self.assertEqual(a["steps"][-1]["models"][name]["numbers"], b["steps"][-1]["models"][name]["numbers"])

    def test_feature_training_excludes_target(self):
        values, _ = matrix(self.draws[:45], self.rules)
        with patch("sklearn.linear_model.LogisticRegression") as estimator:
            ExperimentalModel("logistic", 2).fit(values)
            x, y = estimator.return_value.fit.call_args.args
            np.testing.assert_array_equal(x[0], features(values[:25]))
            np.testing.assert_array_equal(x[-1], features(values[:44]))
            np.testing.assert_array_equal(y, values[25:, -1])

    def test_ml_models_run_and_scores_are_finite(self):
        values, _ = matrix(self.draws[:45], self.rules)
        for name in ("logistic", "random_forest", "gradient_boosting"):
            with self.subTest(model=name):
                model = ExperimentalModel(name, 2).fit(values)
                scores = model.score(values)
                self.assertEqual(scores.shape, (6,))
                self.assertTrue(np.isfinite(scores).all())
                self.assertTrue(((0 <= scores) & (scores <= 1)).all())

    def test_generation_valid_reproducible_and_not_calibrated(self):
        a = generate(self.draws, self.rules, combinations=10)
        self.assertEqual(a, generate(self.draws, self.rules, combinations=10))
        self.assertEqual(len({tuple(ticket["numbers"]) for ticket in a["tickets"]}), 10)
        self.assertTrue(all(len(ticket["numbers"]) == 2 and min(ticket["numbers"]) >= 1 and max(ticket["numbers"]) <= 6 for ticket in a["tickets"]))
        self.assertIn("non sono probabilità", a["notes"])

    def test_ensemble_weights_come_from_validation(self):
        values = np.tile([1, 1, 0, 0, 0, 0], (100, 1)).astype(np.uint8)
        model = ExperimentalModel("ensemble", 2).fit(values)
        self.assertAlmostEqual(sum(model.weights.values()), 1)
        self.assertGreaterEqual(model.validation["steps"], 30)
        self.assertTrue(all(model.validation["p_holm"][model.validation["candidate_names"].index(name)] < .05 for name in model.weights))
        random_values, _ = matrix(self.draws[:100], self.rules)
        random_model = ExperimentalModel("ensemble", 2).fit(random_values)
        self.assertTrue(random_model.validation["fallback_uniform"])
        np.testing.assert_allclose(random_model.score(random_values), np.full(6, 1 / 3))

    def test_predictions_immutable_and_evaluated_on_new_draw(self):
        result = generate(self.draws, self.rules, combinations=2)
        target = datetime.now(timezone.utc) + timedelta(hours=2)
        identifier = save_prediction(self.store, result, "future", target)
        with self.store.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE predictions SET target_id='changed' WHERE id=?", (identifier,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM predictions WHERE id=?", (identifier,))
        actual = Draw("Test", "base", "future", target, tuple(result["tickets"][0]["numbers"]), synthetic=True)
        with patch("games.rules.datetime") as clock:
            clock.now.return_value = target + timedelta(hours=1)
            self.store.add_draw(actual)
        history = self.store.prediction_history()
        self.assertEqual(json.loads(history[0]["matches"])[0], 2)
        self.assertEqual(len(history), 1)

    def test_backdated_predictions_rejected(self):
        result = generate(self.draws, self.rules)
        with self.assertRaises(ValueError):
            save_prediction(self.store, result, "past", datetime(2025, 1, 1, tzinfo=timezone.utc))

    def test_uniform_synthetic_backtest_not_promoted(self):
        result = walk_forward(self.draws, self.rules, initial=60)
        self.assertIn("Nessun algoritmo", result["conclusion"])
        for row in result["summary"]:
            self.assertEqual(sum(row["match_distribution"]), 60)

    def test_model_selection_order_does_not_change_predictions_or_intervals(self):
        first = walk_forward(self.draws[:65], self.rules, ("temporal", "logistic"), initial=50, retrain_every=10)
        second = walk_forward(self.draws[:65], self.rules, ("logistic", "temporal"), initial=50, retrain_every=10)
        for a, b in zip(first["steps"], second["steps"]):
            self.assertEqual(a["models"], b["models"])
        by_name = {row["model"]: row for row in first["summary"]}
        for row in second["summary"]:
            self.assertEqual(by_name[row["model"]], row)

    def test_adding_model_preserves_uniform_and_frequency_baselines(self):
        a = walk_forward(self.draws[:60], self.rules, (), initial=40)
        b = walk_forward(self.draws[:60], self.rules, ("temporal",), initial=40)
        for first, second in zip(a["steps"], b["steps"]):
            for name in ("uniform", "frequency"):
                self.assertEqual(first["models"][name], second["models"][name])
        for name in ("uniform", "frequency"):
            left = next(row for row in a["summary"] if row["model"] == name)
            right = next(row for row in b["summary"] if row["model"] == name)
            self.assertEqual(left["mean_ci95_bootstrap_iid"], right["mean_ci95_bootstrap_iid"])
        self.assertEqual(b["model_names"], ["uniform", "frequency", "temporal"])

    def test_training_requirements_are_checked_before_model_fit(self):
        for names, initial, window in ((("random_forest",), 20, None), (("ensemble",), 80, None),
                                       (("logistic",), 50, 20)):
            with self.assertRaisesRegex(ValueError, "training"):
                walk_forward(self.draws, self.rules, names, initial=initial, train_window=window)


if __name__ == "__main__":
    unittest.main()
