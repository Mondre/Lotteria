import argparse
from dataclasses import asdict
import json
from pathlib import Path

from config.settings import data_directory
from data_sources.connector import ArchiveSource
from data_sources.importer import import_file
from database.store import Store
from games.rules import RuleRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Importazione archivi LottoPredict AI")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--url", help="Fonte HTTPS autorizzata in formato normalizzato")
    parser.add_argument("--format", choices=["csv", "json", "xlsx"])
    parser.add_argument("--synthetic", action="store_true", help="Importa un file nell'archivio sintetico")
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
    if args.url and (not args.format or args.synthetic):
        parser.error("Per URL indicare --format; --synthetic è disponibile solo per file locali")
    store = Store(data_directory() / "lottopredict.sqlite3", RuleRegistry(args.rules) if args.rules else RuleRegistry())
    try:
        report = import_file(store, args.file, args.synthetic) if args.file else ArchiveSource(args.url, args.format).update(store)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(asdict(report), ensure_ascii=False))
    return 2 if report.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
