from datetime import datetime, timezone
import hashlib
import json

import numpy as np

from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry
from lotto_statistics.engine import matrix
from machine_learning.models import ExperimentalModel, top_ticket


def generate(draws: list[Draw], registry: RuleRegistry, model_name: str = "frequency",
             combinations: int = 5, seed: int = 42) -> dict:
    if not 1 <= combinations <= 100:
        raise ValueError("Richiedere da 1 a 100 combinazioni")
    values, rule = matrix(draws, registry)
    from math import comb
    if combinations > comb(values.shape[1], rule["count"]):
        raise ValueError("Troppe combinazioni per le regole selezionate")
    model = ExperimentalModel(model_name, rule["count"], seed).fit(values)
    scores = model.score(values)
    rng = np.random.default_rng(seed)
    tickets = []
    seen = set()
    for attempt in range(10000):
        # Primo ticket: ranking. Gli altri: campionamento pesato (punteggi non calibrati).
        if attempt == 0:
            indices = top_ticket(scores, rule["count"], rng)
        else:
            weights = np.maximum(scores, 1e-6)
            indices = rng.choice(len(scores), rule["count"], replace=False, p=weights / weights.sum())
        numbers = tuple(sorted((indices + rule["minimum"]).tolist()))
        if numbers in seen:
            continue
        seen.add(numbers)
        tickets.append({"numbers": list(numbers), "relative_score": float(scores[indices].mean()),
                        "sum": sum(numbers), "even": sum(n % 2 == 0 for n in numbers)})
        if len(tickets) == combinations:
            break
    if len(tickets) < combinations:
        raise ValueError("Non è stato possibile generare abbastanza combinazioni distinte")
    snapshot = json.dumps([{"id": draw.draw_id, "date": draw.occurred_at.isoformat(),
                            "numbers": draw.numbers, "extras": draw.extras} for draw in draws], sort_keys=True)
    training_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    rules_hash = hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()
    version = hashlib.sha256(f"v1:{model_name}:{seed}:{training_hash}:{rules_hash}".encode()).hexdigest()
    return {"game": draws[0].game, "variant": draws[0].variant, "wheel": draws[0].wheel,
            "synthetic": draws[0].synthetic, "rules_verified": bool(rule["verified"]),
            "model": model_name, "seed": seed, "train_size": len(draws),
            "train_end": draws[-1].occurred_at.isoformat(), "train_last_id": draws[-1].draw_id,
            "training_sha256": training_hash, "rules_sha256": rules_hash,
            "model_version": version, "implementation_version": "1", "tickets": tickets,
            "ensemble_validation": getattr(model, "validation", None),
            "validation": "Nessuna validazione fuori campione associata a questa generazione: eseguire un backtest separato.",
            "random_theoretical_mean_matches": rule["count"] ** 2 / values.shape[1],
            "notes": "Punteggi relativi non calibrati: non sono probabilità di vincita. "
                     "Solo numeri principali, senza extra o Numerone. Nessuna vincita garantita."}


def save_prediction(store: Store, result: dict, target_id: str, target_date: datetime) -> str:
    now = datetime.now(timezone.utc)
    if not target_id.strip() or target_date.tzinfo is None or target_date <= now:
        raise ValueError("Indicare identificativo e data futura con fuso orario")
    if datetime.fromisoformat(result["train_end"]) >= target_date:
        raise ValueError("Il training deve precedere l'estrazione obiettivo")
    # Il payload viene rigenerato e validato dal chiamante; nessuna modifica dopo salvataggio.
    return store.save_prediction(result, target_id.strip(), target_date)
