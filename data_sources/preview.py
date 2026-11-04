"""Anteprima senza modificare archivio o registro, inclusi duplicati interni al file."""
from dataclasses import asdict
import hashlib

from data_sources.importer import parse_record, read_records
from database.store import Store


def preview_content(store: Store, content: bytes, format: str, synthetic: bool = False) -> dict:
    records = read_records(content, format)
    if not records:
        raise ValueError("Il file non contiene estrazioni")
    parsed, failures = {}, {}
    for index, record in enumerate(records, start=1):
        try:
            draw = parse_record(record, "anteprima_web", synthetic)
            store.rules.validate(draw)
            parsed[index] = draw
        except (ValueError, TypeError, OverflowError) as error:
            failures[index] = str(error)[:500]
    known = store.existing_draws(list(parsed.values()))
    result = {"total": len(records), "new": 0, "duplicates": 0, "conflicts": 0, "invalid": 0,
              "sha256": hashlib.sha256(content).hexdigest(), "synthetic": synthetic,
              "sample": [], "errors": [],
              "notes": "Anteprima senza salvataggio. L'archivio viene ricontrollato alla conferma; i conteggi possono cambiare."}
    for index in range(1, len(records) + 1):
        message = ""
        if index in failures:
            classification = "invalid"
            message = failures[index]
            sample = {"row": index}
        else:
            draw = parsed[index]
            key = (draw.game, draw.variant, draw.wheel, draw.draw_id, draw.synthetic)
            previous = known.get(key)
            if previous is None:
                classification = "new"
                known[key] = draw
            elif store.same_content(previous, draw):
                classification = "duplicates"
            else:
                classification = "conflicts"
                message = "Identificativo già presente con contenuto diverso: non verrà sovrascritto"
            sample = {"row": index, **asdict(draw)}
            sample["occurred_at"] = draw.occurred_at.isoformat()
        result[classification] += 1
        if message and len(result["errors"]) < 100:
            result["errors"].append(f"Riga {index}: {message}")
        if len(result["sample"]) < 20:
            result["sample"].append({**sample, "classification": classification, "message": message})
    return result
