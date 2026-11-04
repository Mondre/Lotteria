import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np

from games.models import Draw
from games.rules import RuleRegistry
from lotto_statistics.engine import analyze, holm, matrix, monte_carlo, temporal_tests


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.registry = RuleRegistry()
        self.date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def draw(self, i, numbers):
        return Draw("Lotto", "ordinario", str(i), self.date + timedelta(hours=i),
                    tuple(numbers), "Roma", synthetic=True)

    def test_exact_frequency_delays_and_structures(self):
        draws = [self.draw(0, (1, 2, 3, 4, 5)), self.draw(1, (6, 7, 8, 9, 10)),
                 self.draw(2, (1, 6, 11, 12, 13)), self.draw(3, (6, 7, 8, 9, 10))]
        result = analyze(draws, self.registry)
        number1 = result["frequencies"][0]
        self.assertEqual(number1["count"], 2)
        self.assertEqual(number1["relative"], .5)
        self.assertEqual(number1["windows"]["10"], {"n": 4, "count": 2})
        delay1 = result["delays"][0]
        self.assertEqual((delay1["current"], delay1["max_observed"], delay1["mean_completed"]), (1, 1, 1))
        self.assertEqual(result["delays"][89]["current"], 4)
        self.assertIsNone(result["delays"][89]["mean_completed"])
        self.assertEqual(result["structures"][0]["sum"], 15)
        self.assertEqual(result["structures"][0]["consecutive_pairs"], 4)
        self.assertEqual(result["structures"][2]["repeats_previous"], 1)
        self.assertEqual(result["temporal"]["status"], "not_run")

    def test_holm_known_values(self):
        np.testing.assert_allclose(holm([.01, .04, .03]), [.03, .06, .06])
        self.assertEqual(holm([.001], 100), [.1])

    def test_mixed_or_unsorted_series_rejected(self):
        first = self.draw(0, (1, 2, 3, 4, 5))
        for draws in ([first, replace(self.draw(1, (1, 2, 3, 4, 5)), wheel="Milano")],
                      [first, replace(self.draw(1, (1, 2, 3, 4, 5)), synthetic=False)],
                      [first, first], [self.draw(1, (1, 2, 3, 4, 5)), first], []):
            with self.assertRaises(ValueError):
                matrix(draws, self.registry)

    def test_simulation_reproducible_and_matches_theory(self):
        a = monte_carlo(self.registry, "Lotto", "ordinario", seed=173)
        b = monte_carlo(self.registry, "Lotto", "ordinario", seed=173)
        self.assertEqual(a, b)
        self.assertEqual(sum(a["frequencies"]), 500000)
        standard_error = (a["theoretical_sum_variance"] / a["samples"]) ** .5
        self.assertLess(abs(a["sum_mean"] - a["theoretical_sum_mean"]), 5 * standard_error)
        self.assertLess(abs(a["sum_variance"] / a["theoretical_sum_variance"] - 1), .03)

    def test_uniform_data_not_systematically_flagged(self):
        flagged = 0
        for seed in range(8):
            rng = np.random.default_rng(seed)
            draws = [self.draw(i, (rng.choice(90, 5, replace=False) + 1).tolist()) for i in range(120)]
            result = analyze(draws, self.registry)
            flagged += any(row["p_holm"] < .05 for row in result["frequencies"])
        # Regression check su seed prefissati, non una prova universale del tasso di falsi positivi.
        self.assertLessEqual(flagged, 1)

    def test_temporal_distribution_change_is_detected(self):
        values = np.zeros((100, 4), dtype=np.uint8)
        values[:50, :2] = 1
        values[50:, 2:] = 1
        result = temporal_tests(values)
        self.assertTrue(all(row["p_holm"] < .001 for row in result["half_distribution_change"]))


if __name__ == "__main__":
    unittest.main()
