import numpy as np
from scipy.stats import hypergeom

from games.models import Draw
from games.rules import RuleRegistry
from lotto_statistics.engine import holm, matrix
from machine_learning.models import ExperimentalModel, top_ticket


def null_tail(total_hits: int, steps: int, population: int, count: int) -> float:
    """Coda esatta della somma di corrispondenze sotto estrazioni uniformi indipendenti."""
    one = hypergeom.pmf(np.arange(count + 1), population, count, count)
    distribution = np.array([1.0])
    for _ in range(steps):
        distribution = np.convolve(distribution, one)
    return min(1.0, float(distribution[total_hits:].sum()))


def walk_forward(draws: list[Draw], registry: RuleRegistry, model_names: tuple[str, ...] = ("frequency", "temporal"),
                 initial: int = 700, train_window: int | None = None, retrain_every: int = 10,
                 seed: int = 42, model_factory=ExperimentalModel) -> dict:
    values, rule = matrix(draws, registry)
    n, population = values.shape
    count = rule["count"]
    if not 2 <= initial < n or retrain_every < 1:
        raise ValueError("Finestra iniziale o frequenza di riaddestramento non valida")
    if n - initial > 5000:
        raise ValueError("Massimo 5.000 target per run: ridurre il limite o aumentare il training iniziale")
    if train_window is not None and train_window < 2:
        raise ValueError("Finestra di training troppo piccola")
    if any(draws[i].occurred_at >= draws[i + 1].occurred_at for i in range(n - 1)):
        raise ValueError("Backtest: le date devono essere strettamente crescenti; selezionare una singola serie")
    # Le baseline fanno sempre parte del confronto, senza duplicarle.
    names = list(dict.fromkeys(("uniform", "frequency") + tuple(model_names)))
    models = {name: model_factory(name, count, seed) for name in names}
    # Stream RNG separati: aggiungere un modello non modifica le baseline.
    import hashlib
    randoms = {name: np.random.default_rng(np.random.SeedSequence([seed, int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "little")]))
               for name in names}
    steps = []
    hits = {name: [] for name in names}
    for t in range(initial, n):
        start = max(0, t - train_window) if train_window else 0
        history = values[start:t]
        row = {"target_id": draws[t].draw_id, "target_date": draws[t].occurred_at.isoformat(),
               "train_last_id": draws[t - 1].draw_id, "train_size": len(history), "models": {}}
        for name, model in models.items():
            if (t - initial) % retrain_every == 0:
                model.fit(history.copy())
            scores = model.score(history.copy())
            ticket = top_ticket(scores, count, randoms[name])
            match = int(values[t, ticket].sum())
            hits[name].append(match)
            row["models"][name] = {"numbers": sorted((ticket + rule["minimum"]).tolist()), "matches": match}
        steps.append(row)
    expected = count * count / population
    rng = np.random.default_rng(seed)
    summaries = []
    p_values = []
    for name in names:
        outcomes = np.asarray(hits[name])
        mean = float(outcomes.mean())
        # Bootstrap descrittivo iid; non giustifica causalità né significatività fuori dal modello nullo.
        means = np.asarray([rng.choice(outcomes, len(outcomes), replace=True).mean() for _ in range(1000)])
        ci = np.quantile(means, [.025, .975]).tolist()
        p_value = null_tail(int(outcomes.sum()), len(outcomes), population, count)
        summaries.append({"model": name, "mean_matches": mean, "theoretical_random_mean": expected,
                          "difference_theory": mean - expected,
                          "difference_sampled_random": mean - float(np.mean(hits["uniform"])),
                          "mean_ci95_bootstrap_iid": ci, "p_value": p_value,
                          "match_distribution": np.bincount(outcomes, minlength=count + 1).tolist(),
                          "first_half_mean": float(outcomes[:max(1, len(outcomes) // 2)].mean()),
                          "second_half_mean": float(outcomes[len(outcomes) // 2:].mean())})
        p_values.append(p_value)
    for row, adjusted in zip(summaries, holm(p_values)):
        row["p_holm"] = adjusted
        row["exceeds_uniform_null"] = adjusted < .05 and row["difference_theory"] > 0
    supported = [row["model"] for row in summaries if row["model"] != "uniform" and row["exceeds_uniform_null"]]
    return {"game": draws[0].game, "variant": draws[0].variant, "wheel": draws[0].wheel,
            "synthetic": draws[0].synthetic, "rules_verified": bool(rule["verified"]),
            "initial": initial, "train_window": train_window, "retrain_every": retrain_every,
            "seed": seed, "test_steps": len(steps), "summary": summaries, "steps": steps,
            "conclusion": ("Nessun algoritmo supera il modello casuale nei test eseguiti." if not supported
                           else "Scostamento dal caso nel campione di test: " + ", ".join(supported) +
                           ". Richiede replica indipendente; non dimostra probabilità di vincita future."),
            "notes": ["Parametri fissati prima del test. Non riutilizzare questo test per scegliere iperparametri.",
                      "p-value unilaterali esatti sotto il modello di estrazioni uniformi indipendenti, corretti Holm tra i modelli del run.",
                      "IC bootstrap iid descrittivi: dipendenze temporali possono invalidarne la copertura.",
                      "Confronti tra run esplorativi non sono inclusi nella correzione multipla."]}
