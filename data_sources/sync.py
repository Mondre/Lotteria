"""Aggiornamento su richiesta prima degli esperimenti, con cache persistente."""
from datetime import datetime, timedelta, timezone
from threading import Lock

from data_sources.lotto_official import PAGE, ARCHIVE
from database.store import Store

KEY = "official:lotto:ordinario"


class Synchronizer:
    def __init__(self, store: Store, fetcher=None, enabled: bool = True):
        self.store, self.fetcher = store, fetcher
        self.enabled = enabled
        self.lock = Lock()

    @staticmethod
    def supported(game: str, variant: str) -> bool:
        return (game, variant) == ("Lotto", "ordinario")

    def history(self, game: str, variant: str, wheel: str, limit: int) -> list:
        info = self.store.sync_info(KEY) if self.supported(game, variant) else None
        if not info:
            return []
        identifiers = ["lotto:" + day for day in info.get("covered_days", [])]
        return self.store.history_by_ids(game, variant, wheel, identifiers, limit)

    def ensure(self, game: str, variant: str, wheel: str, limit: int = 1000, force: bool = False) -> dict:
        if not self.enabled:
            return {"state": "disabled", "message": "Aggiornamento ufficiale disattivato nella configurazione."}
        if not self.supported(game, variant):
            return {"state": "unsupported", "message": "Fonte automatica non ancora verificata per questo gioco: si usa l'archivio disponibile."}
        requested = limit
        with self.lock:
            previous = self.store.sync_info(KEY)
            if (not force and previous and previous.get("requested", 0) >= requested
                    and datetime.fromisoformat(previous["checked_at"]) > datetime.now(timezone.utc) - timedelta(hours=1)
                    and self.history(game, variant, wheel, 1)):
                return {**previous, "state": "cached"}
            try:
                if self.fetcher is None:
                    from data_sources.lotto_api import ApiHistory
                    draws, metadata = ApiHistory(self.store).fetch(self.store.rules, requested)
                else:
                    draws, metadata = self.fetcher(self.store.rules, requested)
                # Anche fetcher alternativi devono fornire esclusivamente Lotto reale validato.
                for draw in draws:
                    if draw.synthetic or (draw.game, draw.variant) != (game, variant):
                        raise ValueError("La fonte ha restituito una serie incompatibile")
                    self.store.rules.validate(draw)
                if not draws:
                    raise ValueError("La fonte non ha restituito estrazioni")
                known = self.store.existing_draws(draws)
                new = []
                for draw in draws:
                    key = (draw.game, draw.variant, draw.wheel, draw.draw_id, draw.synthetic)
                    old = known.get(key)
                    if old is not None and not self.store.same_content(old, draw):
                        raise ValueError("Risultato ufficiale diverso dall'archivio locale: verifica necessaria, nessuna sovrascrittura")
                    if old is None:
                        new.append(draw)
                with self.store.batch():
                    inserted = sum(self.store.add_draw(draw) for draw in new) + metadata.get("progressive_inserted", 0)
                    details = {"source_page": PAGE, "source_url": ARCHIVE, **metadata, "requested": requested, "inserted": inserted,
                               "duplicates": len(draws) - inserted, "state": "updated"}
                    self.store.save_sync_info(KEY, details)
                    self.store.log("INFO", f"Aggiornamento Lotto ufficiale: {inserted} aggiunte; ultimo concorso {metadata['latest_day']}")
                return self.store.sync_info(KEY)
            except Exception as error:
                detail = str(error)[:500] if type(error) is ValueError else type(error).__name__
                self.store.log("ERROR", f"Aggiornamento ufficiale fallito ({detail})")
                raise ValueError("Aggiornamento ufficiale non riuscito. " + (detail if isinstance(error, ValueError) else "Verificare rete e disponibilità della fonte.") + " Nessun dato sintetico usato.") from None
