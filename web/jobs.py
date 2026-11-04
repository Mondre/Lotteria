"""Coda locale; risultati scientifici conclusi conservati nel database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from threading import Lock
import uuid

from fastapi import HTTPException

SCIENTIFIC = {"analyze", "generate", "backtest", "simulate"}


class Jobs:
    def __init__(self, store):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lotto-web")
        self.lock = Lock()
        self.items = {}

    def submit(self, operation, function, parameters=None):
        with self.lock:
            if sum(item["status"] in ("queued", "running") for item in self.items.values()) >= 4:
                raise HTTPException(429, "Sono già in corso troppe operazioni. Attendere.")
            while len(self.items) >= 20:
                completed = next((key for key, item in self.items.items() if item["status"] in ("completed", "failed")), None)
                if completed is None:
                    break
                del self.items[completed]
            key = str(uuid.uuid4())
            self.items[key] = {"id": key, "operation": operation, "status": "queued",
                               "request": parameters or {}, "created_at": datetime.now(timezone.utc).isoformat()}
        self.pool.submit(self.run, key, function)
        return {"id": key, "status": "queued"}

    def run(self, key, function):
        with self.lock:
            item = dict(self.items[key])
            self.items[key]["status"] = "running"
        try:
            result = function()
            json.dumps(result, allow_nan=False)
            update = {"status": "completed", "result": result}
        except ValueError as error:
            update = {"status": "failed", "error": str(error)[:1000]}
        except Exception:
            logging.exception("Operazione web fallita")
            update = {"status": "failed", "error": "Operazione non riuscita. Controllare il formato del file e le dipendenze del server."}
        if item["operation"] in SCIENTIFIC:
            try:
                self.store.save_experiment(key, item["operation"], update["status"], item["request"], item["created_at"],
                                           update.get("result"), update.get("error"))
                update["persisted"] = True
            except Exception as error:
                logging.error("Salvataggio esperimento fallito (%s)", type(error).__name__)
                update = {"status": "failed", "persisted": False,
                          "error": "Il risultato non è stato salvato nel database. Riprovare quando la connessione è disponibile."}
        with self.lock:
            self.items[key].update(update)

    def get(self, key):
        with self.lock:
            item = self.items.get(key)
            if item is not None:
                return dict(item)
        try:
            stored = self.store.experiment(key)
        except Exception:
            raise HTTPException(503, "Database momentaneamente non disponibile: riprovare.") from None
        if stored is None:
            raise HTTPException(404, "Operazione non completata o non disponibile. Un calcolo interrotto va rilanciato.")
        return stored
