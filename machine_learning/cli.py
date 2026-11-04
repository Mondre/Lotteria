import argparse
from datetime import datetime
import json

from backtesting.engine import walk_forward
from config.settings import data_directory
from database.store import Store
from games.rules import RuleRegistry
from machine_learning.models import MODELS
from predictions.engine import generate, save_prediction


def main() -> int:
    parser = argparse.ArgumentParser(description="Esperimenti AI e backtesting cronologico")
    parser.add_argument("operation", choices=("generate", "backtest"))
    parser.add_argument("--game", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--wheel", default="")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--model", choices=MODELS, default="frequency")
    parser.add_argument("--models", choices=MODELS, nargs="*", help="Confronto backtest; lista vuota per sole baseline")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--initial", type=int, default=700)
    parser.add_argument("--train-window", type=int)
    parser.add_argument("--retrain-every", type=int, default=10)
    parser.add_argument("--combinations", type=int, default=5)
    parser.add_argument("--target-id")
    parser.add_argument("--target-date")
    args = parser.parse_args()
    if bool(args.target_id) != bool(args.target_date):
        parser.error("--target-id e --target-date devono essere usati insieme")
    if args.operation == "backtest" and args.target_id:
        parser.error("Un backtest non può salvare una previsione futura")
    if args.operation != "backtest" and args.models is not None:
        parser.error("--models è disponibile solo per il backtest")
    registry = RuleRegistry()
    store = Store(data_directory() / "lottopredict.sqlite3", registry)
    try:
        draws = store.history(args.game, args.variant, args.wheel, args.synthetic, args.limit)
        if args.operation == "generate":
            result = generate(draws, registry, args.model, args.combinations, args.seed)
            if args.target_id:
                result["saved_id"] = save_prediction(store, result, args.target_id, datetime.fromisoformat(args.target_date))
        else:
            names = tuple(args.models) if args.models is not None else (args.model,)
            result = walk_forward(draws, registry, names, args.initial, args.train_window, args.retrain_every, args.seed)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (ValueError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
