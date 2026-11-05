from collections import Counter
from itertools import combinations
from math import comb, sqrt

import numpy as np
from scipy.stats import binomtest, fisher_exact

from games.models import Draw
from games.rules import RuleRegistry

WINDOWS = (10, 25, 50, 100, 250, 500, 1000)


def holm(p_values: list[float], total_tests: int | None = None) -> list[float]:
    """Holm-Bonferroni; i test omessi devono avere p=1."""
    total = len(p_values) if total_tests is None else total_tests
    if total < len(p_values):
        raise ValueError("Numero di confronti non valido")
    adjusted = [1.0] * len(p_values)
    maximum = 0.0
    for rank, index in enumerate(sorted(range(len(p_values)), key=p_values.__getitem__)):
        maximum = max(maximum, min(1.0, (total - rank) * p_values[index]))
        adjusted[index] = maximum
    return adjusted


def matrix(draws: list[Draw], registry: RuleRegistry) -> tuple[np.ndarray, dict]:
    if not draws:
        raise ValueError("Nessuna estrazione disponibile per la selezione")
    first = draws[0]
    key = (first.game, first.variant, first.wheel, first.synthetic)
    identifiers = set()
    previous = None
    for draw in draws:
        registry.validate(draw)
        if (draw.game, draw.variant, draw.wheel, draw.synthetic) != key:
            raise ValueError("Non mescolare giochi, varianti, ruote o dati reali e sintetici")
        if draw.draw_id in identifiers:
            raise ValueError("Identificativo duplicato nella serie")
        if previous is not None and draw.occurred_at < previous:
            raise ValueError("Le estrazioni devono essere ordinate cronologicamente")
        previous = draw.occurred_at
        identifiers.add(draw.draw_id)
    rule = registry.rules[(first.game, first.variant)]
    values = np.zeros((len(draws), rule["maximum"] - rule["minimum"] + 1), dtype=np.uint8)
    for i, draw in enumerate(draws):
        values[i, np.asarray(draw.numbers) - rule["minimum"]] = 1
    return values, rule


def analyze(draws: list[Draw], registry: RuleRegistry) -> dict:
    values, rule = matrix(draws, registry)
    n, population = values.shape
    k, start = rule["count"], rule["minimum"]
    p = k / population
    counts = values.sum(axis=0)
    # At most 201 chronological checkpoints, including first and last draws.
    checkpoints = np.unique(np.linspace(1, n, min(n, 201), dtype=int))
    cumulative = values.cumsum(axis=0)
    raw = [float(binomtest(int(count), n, p).pvalue) for count in counts]
    corrected = holm(raw)
    frequency = []
    delays = []
    for column, count in enumerate(counts):
        observed = float(count) / n
        z = 1.959963984540054
        denominator = 1 + z * z / n
        center = (observed + z * z / (2 * n)) / denominator
        margin = z * sqrt(observed * (1 - observed) / n + z * z / (4 * n * n)) / denominator
        frequency.append({"number": column + start, "count": int(count), "relative": observed,
                          "expected_count": n * p, "std_count": sqrt(n * p * (1 - p)),
                          "z": (int(count) - n * p) / sqrt(n * p * (1 - p)) if p < 1 else None,
                          "ci95": [max(0.0, center - margin), min(1.0, center + margin)],
                          "p_value": raw[column], "p_holm": corrected[column],
                          "trajectory": [{"draws": int(step), "relative": float(cumulative[step - 1, column]) / int(step)}
                                         for step in checkpoints],
                          "windows": {str(window): {"n": min(n, window), "count": int(values[-window:, column].sum())}
                                      for window in WINDOWS}})
        hits = np.flatnonzero(values[:, column])
        completed = np.diff(hits) - 1
        gaps = np.diff(np.r_[-1, hits, n]) - 1
        delays.append({"number": column + start,
                       "current": n - 1 - int(hits[-1]) if len(hits) else n,
                       "max_observed": int(gaps.max()),
                       "mean_completed": float(completed.mean()) if len(completed) else None,
                       "completed_gaps": completed.tolist(), "boundary_gaps_censored": True,
                       "theoretical_mean": (1 - p) / p})
    structures = []
    for i, draw in enumerate(draws):
        numbers = sorted(draw.numbers)
        structures.append({"draw_id": draw.draw_id, "sum": sum(numbers),
                           "even": sum(number % 2 == 0 for number in numbers),
                           "low": sum(number < start + population / 2 for number in numbers),
                           "consecutive_pairs": sum(b - a == 1 for a, b in zip(numbers, numbers[1:])),
                           "distances": [b - a for a, b in zip(numbers, numbers[1:])],
                           "repeats_previous": len(set(numbers) & set(draws[i - 1].numbers)) if i else None,
                           "bands": [sum(start + population * band / 5 <= number < start + population * (band + 1) / 5
                                         for number in numbers) for band in range(5)]})
    result = {"draws": n, "game": draws[0].game, "variant": draws[0].variant,
              "wheel": draws[0].wheel, "synthetic": draws[0].synthetic,
              "rules_verified": bool(rule["verified"]), "frequencies": frequency,
              "delays": delays, "structures": structures,
              "extras_analysis": describe_extras(draws, rule),
              "notes": ["Un ritardo elevato non aumenta la probabilità della prossima uscita.",
                        "Intervalli Wilson marginali al 95%; frequenze con p-value corretti Holm nella famiglia dei numeri.",
                        "Coppie e terzine: test unilaterali corretti su tutte le combinazioni, in famiglie separate.",
                        "Questi test non dimostrano prevedibilità; nessun modello predittivo è qui validato.",
                        "Test sui soli numeri principali; gli extra configurati hanno conteggi descrittivi separati."]}
    for size, name in ((2, "pairs"), (3, "triples")):
        counter = Counter(combo for draw in draws for combo in combinations(sorted(draw.numbers), size))
        inclusion = comb(k, size) / comb(population, size) if k >= size else 0
        entries = list(counter.items())
        # Le combinazioni non osservate hanno p=1; incluse nel numero totale dei confronti.
        cache = {count: float(binomtest(count, n, inclusion, alternative="greater").pvalue)
                 for count in set(counter.values())}
        ps = [cache[count] for _, count in entries]
        qs = holm(ps, comb(population, size))
        result[name] = sorted([{"numbers": list(combo), "count": count, "p_value": pv, "p_holm": qv}
                              for (combo, count), pv, qv in zip(entries, ps, qs)],
                             key=lambda row: (-row["count"], row["numbers"]))[:50]
    result["temporal"] = temporal_tests(values)
    return result


def describe_extras(draws: list[Draw], rule: dict) -> dict:
    """Descrizione marginale dei soli extra configurati, senza ipotesi sul caso."""
    results = {}
    for name, specification in rule["extras"].items():
        counts = Counter(draw.extras[name] for draw in draws)
        results[name] = {
            "draws": len(draws), "minimum": specification["minimum"],
            "maximum": specification["maximum"], "rules_verified": bool(rule["verified"]),
            "frequencies": [{"number": number, "count": counts[number],
                             "relative": counts[number] / len(draws)}
                            for number in range(specification["minimum"], specification["maximum"] + 1)],
            "notes": "Conteggi marginali descrittivi, separati dai numeri principali. "
                     "Nessuna indipendenza o distribuzione uniforme presupposta; "
                     "non sono probabilità future. Regole degli extra non verificate."
        }
    return results


def temporal_tests(values: np.ndarray, permutations: int = 199, seed: int = 42) -> dict:
    n, population = values.shape
    if n < 20:
        return {"status": "not_run", "reason": "Servono almeno 20 estrazioni per i test temporali"}
    if n > 10000:
        return {"status": "not_run", "reason": "Test a permutazioni limitato a 10.000 estrazioni: ridurre la finestra"}
    split = n // 2
    counts = values.sum(axis=0).astype(float)
    change_ps = []
    for column in range(population):
        first, second = int(values[:split, column].sum()), int(values[split:, column].sum())
        change_ps.append(float(fisher_exact([[first, split - first], [second, n - split - second]]).pvalue))
    lags = [lag for lag in (1, 2, 5, 10) if lag < n]
    # Sovrapposizione media rispetto all'ordine casuale dello stesso archivio.
    expectation = float(np.sum(counts * (counts - 1)) / (n * (n - 1)))
    def overlaps(array):
        return np.asarray([np.sum(array[:-lag] * array[lag:], axis=1).mean() for lag in lags])
    observed = overlaps(values)
    exceed = np.zeros(len(lags), dtype=int)
    rng = np.random.default_rng(seed)
    for _ in range(permutations):
        simulated = overlaps(values[rng.permutation(n)])
        exceed += np.abs(simulated - expectation) >= np.abs(observed - expectation) - 1e-12
    ps = ((exceed + 1) / (permutations + 1)).tolist()
    corrected = holm(ps)
    return {"status": "completed", "seed": seed, "permutations": permutations,
            "lag_overlap": [{"lag": lag, "mean": float(mean), "p_value": pv, "p_holm": qv}
                            for lag, mean, pv, qv in zip(lags, observed, ps, corrected)],
            "half_distribution_change": [{"number_index": column, "p_value": pv, "p_holm": qv}
                                         for column, (pv, qv) in enumerate(zip(change_ps, holm(change_ps)))],
            "notes": "Test esplorativi: sovrapposizioni a lag prefissati con permutazioni e cambiamento tra due metà (Fisher). "
                     "Famiglie Holm separate; non sono una ricerca esaustiva di periodicità o una prova di prevedibilità."}


def monte_carlo(registry: RuleRegistry, game: str, variant: str,
                samples: int = 100000, seed: int = 42) -> dict:
    if not 100000 <= samples <= 1000000:
        raise ValueError("Usare da 100.000 a 1.000.000 di simulazioni")
    rule = registry.rules[(game, variant)]
    start, stop, count = rule["minimum"], rule["maximum"], rule["count"]
    population = stop - start + 1
    rng = np.random.default_rng(seed)
    frequencies = np.zeros(population, dtype=np.int64)
    total_sum = 0.0
    total_square = 0.0
    for offset in range(0, samples, 2000):
        batch = min(2000, samples - offset)
        indices = np.argpartition(rng.random((batch, population)), count - 1, axis=1)[:, :count]
        frequencies += np.bincount(indices.ravel(), minlength=population)
        sums = (indices + start).sum(axis=1)
        total_sum += float(sums.sum())
        total_square += float(np.square(sums.astype(float)).sum())
    mean = total_sum / samples
    return {"samples": samples, "seed": seed, "game": game, "variant": variant,
            "minimum": start,
            "synthetic": True, "frequencies": frequencies.tolist(),
            "expected_frequency": samples * count / population,
            "sum_mean": mean, "sum_variance": total_square / samples - mean * mean,
            "theoretical_sum_mean": count * (start + stop) / 2,
            "theoretical_sum_variance": count * (population - count) * (population + 1) / 12,
            "notes": "Simulazione dei soli numeri principali; non è una previsione."}
