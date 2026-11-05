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
             combinations: int = 5, seed: int = 42, ticket_strategy: str = "weighted", include_numerone: bool = False) -> dict:
    if not 1 <= combinations <= 100:
        raise ValueError("Richiedere da 1 a 100 combinazioni")
    values, rule = matrix(draws, registry)
    if include_numerone and (draws[0].game, draws[0].variant) != ("Win for Life", "classico"):
        raise ValueError("Numerone disponibile solo per Win for Life Classico")
    from math import comb
    if combinations > comb(values.shape[1], rule["count"]):
        raise ValueError("Troppe combinazioni per le regole selezionate")
    if ticket_strategy not in ("weighted", "disjoint"):
        raise ValueError("Strategia di combinazioni non supportata")
    if ticket_strategy == "disjoint" and combinations * rule["count"] > values.shape[1]:
        raise ValueError(f"Senza sovrapposizioni: massimo {values.shape[1] // rule['count']} combinazioni per questa serie")
    model = ExperimentalModel(model_name, rule["count"], seed).fit(values)
    scores = model.score(values)
    rng = np.random.default_rng(seed)
    tickets = []
    seen = set()
    used_indices = set()
    for attempt in range(10000):
        # Primo ticket: ranking. Gli altri: campionamento pesato (punteggi non calibrati).
        if attempt == 0:
            indices = top_ticket(scores, rule["count"], rng)
        elif ticket_strategy == "disjoint":
            available = np.array([index for index in range(len(scores)) if index not in used_indices])
            weights = np.maximum(scores[available], 1e-6)
            indices = rng.choice(available, rule["count"], replace=False, p=weights / weights.sum())
        else:
            weights = np.maximum(scores, 1e-6)
            indices = rng.choice(len(scores), rule["count"], replace=False, p=weights / weights.sum())
        numbers = tuple(sorted((indices + rule["minimum"]).tolist()))
        if numbers in seen:
            continue
        seen.add(numbers)
        used_indices.update(map(int, indices))
        tickets.append({"numbers": list(numbers), "relative_score": float(scores[indices].mean()),
                        "sum": sum(numbers), "even": sum(n % 2 == 0 for n in numbers)})
        if len(tickets) == combinations:
            break
    if len(tickets) < combinations:
        raise ValueError("Non è stato possibile generare abbastanza combinazioni distinte")
    numerone = None
    if include_numerone:
        from winforlife.engine import add_numerone
        numerone = add_numerone(tickets, draws, rule, model_name, seed)
    snapshot = json.dumps([{"id": draw.draw_id, "date": draw.occurred_at.isoformat(),
                            "numbers": draw.numbers, "extras": draw.extras, "date_precision": draw.date_precision} for draw in draws], sort_keys=True)
    training_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    rules_hash = hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()
    implementation = "1" if ticket_strategy == "weighted" else "2-disjoint"
    version_prefix = "v1" if ticket_strategy == "weighted" else "v2-disjoint"
    if include_numerone:
        implementation = "3-wfl-" + ticket_strategy
        version_prefix = "v3-wfl-" + ticket_strategy
    version = hashlib.sha256(f"{version_prefix}:{model_name}:{seed}:{training_hash}:{rules_hash}".encode()).hexdigest()
    distinct = len({number for ticket in tickets for number in ticket["numbers"]})
    coverage = {"distinct_numbers": distinct, "slots": combinations * rule["count"],
                "repeated_slots": combinations * rule["count"] - distinct,
                "theoretical_any_number_under_uniform": 1 - comb(values.shape[1] - distinct, rule["count"]) / comb(values.shape[1], rule["count"])}
    return {"game": draws[0].game, "variant": draws[0].variant, "wheel": draws[0].wheel,
            "synthetic": draws[0].synthetic, "rules_verified": bool(rule["verified"]),
            "model": model_name, "seed": seed, "train_size": len(draws),
            "train_end": draws[-1].occurred_at.isoformat(), "train_last_id": draws[-1].draw_id,
            "train_end_precision": draws[-1].date_precision,
            "training_sha256": training_hash, "rules_sha256": rules_hash,
            "model_version": version, "implementation_version": implementation, "tickets": tickets,
            "ticket_strategy": ticket_strategy, "coverage": coverage,
            "include_numerone": include_numerone, "numerone": numerone,
            "ensemble_validation": getattr(model, "validation", None),
            "validation": "Nessuna validazione fuori campione associata a questa generazione: eseguire un backtest separato.",
            "random_theoretical_mean_matches": rule["count"] ** 2 / values.shape[1],
            "notes": "Punteggi relativi non calibrati: non sono probabilità di vincita. "
                     + ("Win for Life Classico: 10 numeri principali e Numerone separato; il Numerone usa frequenze regolarizzate (o uniforme/temporale), non i modelli ML dei principali. Premi non verificati. " if include_numerone else "Solo numeri principali, senza extra o Numerone. ")
                     + "Nessuna vincita garantita. "
                     + ("Numeri disgiunti tra combinazioni: maggiore copertura, non maggiore prevedibilità. " if ticket_strategy == "disjoint" else "")
                     + ("Le date dello storico non indicano un'ora osservata. Le previsioni emesse nel giorno del risultato "
                        "possono non essere valutabili automaticamente." if any(draw.date_precision == "date" for draw in draws) else "")}


def save_prediction(store: Store, result: dict, target_id: str, target_date: datetime) -> str:
    now = datetime.now(timezone.utc)
    if not target_id.strip() or target_date.tzinfo is None or target_date <= now:
        raise ValueError("Indicare identificativo e data futura con fuso orario")
    if datetime.fromisoformat(result["train_end"]) >= target_date:
        raise ValueError("Il training deve precedere l'estrazione obiettivo")
    # Il payload viene rigenerato e validato dal chiamante; nessuna modifica dopo salvataggio.
    return store.save_prediction(result, target_id.strip(), target_date)
