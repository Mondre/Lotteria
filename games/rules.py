import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from games.models import Draw

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "config" / "games.json"


class RuleRegistry:
    def __init__(self, path: Path = DEFAULT_RULES):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("Versione configurazione regole non supportata")
        self.rules: dict[tuple[str, str], dict[str, Any]] = {}
        for rule in payload["rules"]:
            key = (rule["game"], rule["variant"])
            if key in self.rules:
                raise ValueError("Regola duplicata")
            if not (type(rule["minimum"]) is int and type(rule["maximum"]) is int
                    and type(rule["count"]) is int
                    and 1 <= rule["count"] <= rule["maximum"] - rule["minimum"] + 1):
                raise ValueError("Intervallo o numerosità della regola non validi")
            self.rules[key] = rule

    def validate(self, draw: Draw) -> None:
        rule = self.rules.get((draw.game, draw.variant))
        if rule is None:
            raise ValueError("Gioco o variante non supportati")
        if not draw.draw_id.strip() or not draw.source.strip():
            raise ValueError("Identificativo e fonte sono obbligatori")
        if draw.occurred_at.tzinfo is None or draw.occurred_at.utcoffset() is None:
            raise ValueError("La data deve includere il fuso orario")
        if draw.occurred_at > datetime.now(timezone.utc):
            raise ValueError("Estrazione nel futuro")
        if draw.date_precision not in ("instant", "date"):
            raise ValueError("Precisione della data non valida")
        if draw.date_precision == "date":
            local = draw.occurred_at.astimezone(ZoneInfo("Europe/Rome"))
            if any((local.hour, local.minute, local.second, local.microsecond)):
                raise ValueError("Una data senza orario deve usare mezzanotte Europe/Rome come riferimento")
        if len(draw.numbers) != rule["count"] or len(set(draw.numbers)) != len(draw.numbers):
            raise ValueError("Numerosità errata o numeri duplicati")
        if any(type(n) is not int or not rule["minimum"] <= n <= rule["maximum"] for n in draw.numbers):
            raise ValueError("Numero fuori intervallo")
        if rule["wheels"]:
            if draw.wheel not in rule["wheels"]:
                raise ValueError("Ruota non valida")
        elif draw.wheel:
            raise ValueError("Questo gioco non prevede ruote")
        if set(draw.extras) != set(rule["extras"]):
            raise ValueError("Campi aggiuntivi mancanti o sconosciuti")
        for name, spec in rule["extras"].items():
            number = draw.extras[name]
            if type(number) is not int or not spec["minimum"] <= number <= spec["maximum"]:
                raise ValueError(f"{name}: valore non valido")
            if spec["distinct_main"] and number in draw.numbers:
                raise ValueError(f"{name}: deve essere distinto dai numeri principali")
