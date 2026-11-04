"""Genera un archivio demo esplicitamente sintetico, senza scrivere nel database."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random

from games.rules import RuleRegistry


def demo_records(count: int = 1000, seed: int = 42) -> list[dict]:
    if not 1 <= count <= 100000:
        raise ValueError("Richiedere da 1 a 100.000 estrazioni demo")
    rng = random.Random(seed)
    records = []
    # Demo Lotto/Roma; la data non indica un calendario ufficiale.
    end = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rule = RuleRegistry().rules[("Lotto", "ordinario")]
    for index in range(count):
        records.append({"game": "Lotto", "variant": "ordinario", "wheel": "Roma",
                        "draw_id": f"SYNTHETIC-{seed}-{index:06}",
                        "occurred_at": (end - timedelta(hours=count - index)).isoformat(),
                        "numbers": sorted(rng.sample(range(rule["minimum"], rule["maximum"] + 1), rule["count"])),
                        "extras": {}, "synthetic": True, "source": "SYNTHETIC_DEMO"})
    return records


def main():
    parser = argparse.ArgumentParser(description="Generatore di dati SINTETICI, non estrazioni reali")
    parser.add_argument("output", type=Path)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Il file esiste già: scegliere un nuovo percorso")
    args.output.write_text(json.dumps(demo_records(args.count, args.seed), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
