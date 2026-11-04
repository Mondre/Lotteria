import argparse
import json

from config.settings import data_directory
from database.store import Store
from games.rules import RuleRegistry
from lotto_statistics.engine import analyze, monte_carlo


def main() -> int:
    parser = argparse.ArgumentParser(description="Analisi descrittiva e simulazione LottoPredict AI")
    parser.add_argument("--game", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--wheel", default="")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--monte-carlo", action="store_true")
    parser.add_argument("--samples", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    registry = RuleRegistry()
    try:
        if args.monte_carlo:
            result = monte_carlo(registry, args.game, args.variant, args.samples, args.seed)
        else:
            store = Store(data_directory() / "lottopredict.sqlite3", registry)
            result = analyze(store.history(args.game, args.variant, args.wheel, args.synthetic, args.limit), registry)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (ValueError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
