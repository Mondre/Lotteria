"""Avvio desktop o verifica del database senza Qt."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler

from config.settings import data_directory
from database.store import Store
from games.rules import RuleRegistry


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"time": self.formatTime(record), "level": record.levelname,
                   "message": record.getMessage()}
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="LottoPredict AI")
    parser.add_argument("--check", action="store_true", help="Inizializza e verifica il database senza GUI")
    parser.add_argument("--rules", type=str, help="Percorso a una configurazione regole JSON personalizzata")
    parser.add_argument("--smoke-test", action="store_true", help="Avvia Qt e termina automaticamente")
    args = parser.parse_args()
    folder = data_directory()
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "application.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    from pathlib import Path
    rules = RuleRegistry(Path(args.rules)) if args.rules else RuleRegistry()
    store = Store(folder / "lottopredict.sqlite3", rules)
    if args.check:
        with store.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        print(json.dumps({"database": str(store.path), "integrity": integrity, "real_draws": store.count(), "synthetic_draws": store.count(True)}, ensure_ascii=False))
        return 0 if integrity == "ok" else 1
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from ui.window import MainWindow
    app = QApplication([])
    window = MainWindow(store)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(250, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
