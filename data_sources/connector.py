"""Connettore HTTPS per archivi normalizzati da una fonte autorizzata dall'utente."""
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, build_opener
import ssl

from data_sources.importer import MAX_BYTES, ImportReport, import_content
from database.store import Store


class SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("Redirect verso HTTP non consentito")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class ArchiveSource:
    url: str
    format: str

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Usare un URL HTTPS senza credenziali incorporate")
        if self.format not in ("csv", "json", "xlsx"):
            raise ValueError("Formato archivio non supportato")

    def update(self, store: Store) -> ImportReport:
        opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), SecureRedirect())
        try:
            with opener.open(self.url, timeout=30) as response:
                content = response.read(MAX_BYTES + 1)
        except Exception as error:
            # Gli URL possono contenere parametri sensibili: non registrarli.
            store.log("ERROR", f"Download archivio fallito ({type(error).__name__})")
            raise RuntimeError("Download fallito: verificare rete, autorizzazioni e formato della fonte") from None
        return import_content(store, content, self.format,
                              f"https:{urlsplit(self.url).hostname}")
