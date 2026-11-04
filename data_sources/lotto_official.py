"""Storico scaricabile collegato dal sito ufficiale; nessun endpoint ipotizzato."""
from collections import defaultdict
from datetime import datetime, time
from html.parser import HTMLParser
import io
import re
import ssl
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from games.models import Draw
from games.rules import RuleRegistry

PAGE = "https://www.lotto-italia.it/lotto/estratti-ruote"
ARCHIVE = "https://www.brightstarlottery.it/STORICO_ESTRAZIONI_LOTTO/storico01-oggi.zip"
ALLOWED_HOSTS = {"www.lotto-italia.it", "lotto-italia.it", "www.brightstarlottery.it"}
WHEELS = {"BA": "Bari", "CA": "Cagliari", "FI": "Firenze", "GE": "Genova", "MI": "Milano",
          "NA": "Napoli", "PA": "Palermo", "RM": "Roma", "TO": "Torino", "VE": "Venezia",
          "RN": "Nazionale", "NZ": "Nazionale"}


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.port not in (None, 443)
            or parts.username or parts.password):
        raise ValueError("La fonte ufficiale rimanda a un dominio non consentito")


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, limit: int) -> bytes:
    check_url(url)
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), OfficialRedirect())
    request = Request(url, headers={"User-Agent": "LottoPredictAI/0.1 (personal statistical archive)"})
    with opener.open(request, timeout=30) as response:
        check_url(response.geturl())
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Il download ufficiale supera il limite previsto")
    return data


class ArchiveLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if urlsplit(urljoin(PAGE, href)).path.endswith("/storico01-oggi.zip"):
                url = urljoin(PAGE, href)
                check_url(url)
                self.urls.append(url)


def archive_url(page: bytes) -> str:
    parser = ArchiveLinks()
    parser.feed(page.decode("utf-8"))
    urls = list(dict.fromkeys(parser.urls))
    if len(urls) != 1:
        raise ValueError("Il collegamento allo storico ufficiale è cambiato: aggiornamento sospeso")
    return urls[0]


def parse_archive(content: bytes, registry: RuleRegistry, limit: int = 1000) -> tuple[list[Draw], dict]:
    if not 1 <= limit <= 10000:
        raise ValueError("Finestra automatica da 1 a 10.000 estrazioni")
    groups = defaultdict(dict)
    lines = 0
    with ZipFile(io.BytesIO(content)) as archive:
        files = [entry for entry in archive.infolist() if not entry.is_dir() and not entry.filename.startswith("__MACOSX/")]
        if not 1 <= len(files) <= 4 or sum(entry.file_size for entry in files) > 32 * 1024 * 1024:
            raise ValueError("Struttura o dimensione dell'archivio ZIP non valida")
        for entry in files:
            if not entry.filename.lower().endswith(".txt"):
                raise ValueError("L'archivio ufficiale non contiene il formato testuale atteso")
            text = archive.read(entry).decode("utf-8-sig")
            for line in text.splitlines():
                if not line.strip():
                    continue
                lines += 1
                if lines > 150000:
                    raise ValueError("Troppe righe nell'archivio ufficiale")
                fields = re.split(r"[\t ;,]+", line.strip())
                if len(fields) != 7:
                    raise ValueError(f"Formato storico non riconosciuto alla riga {lines}")
                day = None
                for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        day = datetime.strptime(fields[0], fmt).date()
                        break
                    except ValueError:
                        pass
                wheel = WHEELS.get(fields[1].upper())
                if day is None or wheel is None or not all(value.isascii() and value.isdigit() for value in fields[2:]):
                    raise ValueError(f"Data, ruota o numeri non riconosciuti alla riga {lines}")
                if day > datetime.now(ZoneInfo("Europe/Rome")).date():
                    raise ValueError("Lo storico ufficiale contiene date future")
                numbers = tuple(map(int, fields[2:]))
                if day in groups[wheel] and groups[wheel][day] != numbers:
                    raise ValueError("Lo storico contiene risultati incompatibili per la stessa ruota e data")
                groups[wheel][day] = numbers
    expected = registry.rules[("Lotto", "ordinario")]["wheels"]
    if set(groups) != set(expected):
        raise ValueError("Lo storico non contiene tutte le undici ruote previste")
    common = set.intersection(*(set(groups[wheel]) for wheel in expected))
    # Solo concorsi completi; niente mescolanza con ruote mancanti o aggiornamenti parziali.
    days = sorted(common)[-limit:]
    if not days:
        raise ValueError("Nessun concorso completo disponibile nello storico")
    result = []
    for day in days:
        for wheel in expected:
            draw = Draw("Lotto", "ordinario", "lotto:" + day.isoformat(),
                        datetime.combine(day, time.min, ZoneInfo("Europe/Rome")), groups[wheel][day], wheel,
                        {}, False, ARCHIVE, "date")
            registry.validate(draw)
            result.append(draw)
    return result, {"available": len(common), "selected_per_wheel": len(days), "latest_day": days[-1].isoformat(),
                    "covered_days": [day.isoformat() for day in days],
                    "date_precision": "date", "partial_latest": max(max(values) for values in groups.values()) > days[-1]}


def fetch_archive(registry: RuleRegistry, limit: int = 1000) -> tuple[list[Draw], dict]:
    page = download(PAGE, 2 * 1024 * 1024)
    url = archive_url(page)
    content = download(url, 8 * 1024 * 1024)
    draws, metadata = parse_archive(content, registry, limit)
    from dataclasses import replace
    draws = [replace(draw, source=url) for draw in draws]
    return draws, {**metadata, "source_page": PAGE, "source_url": url}
