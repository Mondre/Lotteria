"""Connettore progressivo per i servizi pubblici usati dalla pagina ufficiale."""
from datetime import date, datetime, timedelta
import hashlib
import json
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener
from zoneinfo import ZoneInfo

from data_sources.importer import unique_fields
from data_sources.lotto_official import OfficialRedirect, PAGE, WHEELS, check_url
from games.models import Draw

BASE = 'https://www.lotto-italia.it/gdl/estrazioni-e-vincite/'
CALENDAR = 'calendario-estrazioni-del-lotto.json'
EXTRACTION = 'estrazioni-del-lotto.json'
PROGRESS_KEY = 'official:lotto:api:progress'
DAY_PREFIX = 'official:lotto:api:day:'
ROME = ZoneInfo('Europe/Rome')


class UnavailableDraw(ValueError):
    pass


class IncompleteDraw(ValueError):
    pass


def post(name, body):
    if name not in (CALENDAR, EXTRACTION):
        raise ValueError('Servizio ufficiale non consentito')
    url = BASE + name
    check_url(url)
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), OfficialRedirect())
    request = Request(url, data=json.dumps(body).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'User-Agent': 'LottoPredictAI/0.1 (personal statistical archive)'})
    for attempt in range(3):
        try:
            with opener.open(request, timeout=20) as response:
                check_url(response.geturl())
                content = response.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError('Risposta ufficiale troppo grande')
            return json.loads(content, object_pairs_hook=unique_fields), hashlib.sha256(content).hexdigest()
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = error.headers.get('Retry-After', '') if error.headers else ''
            if delay.isdigit() and int(delay) > 10:
                raise ValueError('La fonte richiede di riprovare più tardi') from None
            time.sleep(int(delay) if delay.isdigit() else min(2 ** attempt, 4))
        except URLError as error:
            if isinstance(error.reason, ssl.SSLError) or attempt == 2 or '403' in str(error):
                raise
            time.sleep(min(2 ** attempt, 4))


def parse_extraction(payload, day, registry):
    if not isinstance(payload, dict) or payload.get('esito') != 'OK':
        raise UnavailableDraw(f'Concorso {day.isoformat()} non disponibile nella fonte')
    if type(payload.get('data')) is not int:
        raise ValueError('Data del concorso non riconosciuta')
    reference = datetime.fromtimestamp(payload['data'] / 1000, ROME)
    if reference.date() != day or day > datetime.now(ROME).date():
        raise ValueError('Data della risposta diversa da quella richiesta o futura')
    rows = payload.get('estrazione')
    if not isinstance(rows, list) or len(rows) != 11:
        raise IncompleteDraw('Concorso ufficiale incompleto')
    draws = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Formato della ruota non riconosciuto')
        wheel, numbers = WHEELS.get(row.get('ruota')), row.get('numeri')
        if wheel is None or not isinstance(numbers, list):
            raise ValueError('Ruota o numeri ufficiali non riconosciuti')
        draw = Draw('Lotto', 'ordinario', 'lotto:' + day.isoformat(),
                    datetime(day.year, day.month, day.day, tzinfo=ROME), tuple(numbers), wheel,
                    source=BASE + EXTRACTION, date_precision='date')
        registry.validate(draw)
        draws.append(draw)
    if {draw.wheel for draw in draws} != set(registry.rules[('Lotto', 'ordinario')]['wheels']):
        raise ValueError('Ruote ufficiali duplicate o mancanti')
    return draws


class ApiHistory:
    def __init__(self, store, requester=post, today=None):
        self.store, self.requester = store, requester
        self.today = today or datetime.now(ROME).date()

    def fetch(self, registry, limit):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError('Finestra ufficiale da 1 a 10.000 concorsi')
        month = self.today.replace(day=1)
        all_draws, covered = [], []
        inserted, downloaded, reused = 0, 0, 0
        partial_latest = False

        def progress(state, error=None):
            self.store.save_sync_info(PROGRESS_KEY, {
                'state': state, 'requested': limit, 'completed': len(covered),
                'downloaded': downloaded, 'reused': reused, 'inserted': inserted,
                'oldest_day': covered[-1] if covered else None,
                'latest_day': covered[0] if covered else None,
                'message': error, 'source_url': BASE + EXTRACTION})

        progress('running')
        try:
            # All eleven current wheels exist only from May 2005. Never invent earlier coverage.
            while month >= date(2005, 5, 1) and len(covered) < limit:
                days, _ = self.requester(CALENDAR, {'anno': str(month.year), 'mese': f'{month.month:02d}'})
                if (not isinstance(days, list) or any(type(day) is not int or not 1 <= day <= 31 for day in days)
                        or len(set(days)) != len(days)):
                    raise ValueError('Formato del calendario ufficiale cambiato')
                dates = sorted((date(month.year, month.month, day) for day in days), reverse=True)
                for day in dates:
                    if day > self.today or day < date(2005, 5, 4):
                        continue
                    receipt = self.store.sync_info(DAY_PREFIX + day.isoformat())
                    # Recheck the two newest results for corrections; older validated days resume locally.
                    cached = receipt is not None and len(covered) >= 2
                    if cached:
                        payload, digest = receipt['payload'], receipt['sha256']
                    else:
                        payload, digest = self.requester(EXTRACTION, {'data': day.strftime('%Y%m%d')})
                    try:
                        draws = parse_extraction(payload, day, registry)
                    except (UnavailableDraw, IncompleteDraw):
                        if day == self.today:
                            partial_latest = True
                            continue
                        raise
                    known = self.store.existing_draws(draws)
                    for draw in draws:
                        key = (draw.game, draw.variant, draw.wheel, draw.draw_id, draw.synthetic)
                        previous = known.get(key)
                        if previous and not self.store.same_content(previous, draw):
                            raise ValueError(f'Risultato ufficiale in conflitto per {day}: nessuna sovrascrittura')
                    with self.store.batch():
                        added = sum(self.store.add_draw(draw) for draw in draws)
                        if not cached:
                            self.store.save_sync_info(DAY_PREFIX + day.isoformat(), {'payload': payload, 'sha256': digest})
                    inserted += added
                    downloaded += not cached
                    reused += cached
                    covered.append(day.isoformat())
                    all_draws.extend(draws)
                    progress('running')
                    if len(covered) == limit:
                        break
                month = (month - timedelta(days=1)).replace(day=1)
            if len(covered) < limit:
                raise ValueError(f'La fonte copre {len(covered)} concorsi completi, richiesti {limit}')
        except Exception as error:
            detail = str(error)[:300] if isinstance(error, ValueError) else type(error).__name__
            progress('failed', detail)
            raise ValueError(f'Aggiornamento incompleto: {len(covered)} di {limit} concorsi. '
                             f'I giorni validati sono conservati e riutilizzabili. {detail}') from None
        progress('completed')
        return sorted(all_draws, key=lambda draw: (draw.occurred_at, draw.wheel)), {
            'source_page': PAGE, 'source_url': BASE + EXTRACTION, 'connector': 'official_api_v1',
            'selected_per_wheel': len(covered), 'latest_day': covered[0],
            'covered_days': sorted(covered), 'date_precision': 'date', 'partial_latest': partial_latest,
            'downloaded_days': downloaded, 'reused_days': reused, 'progressive_inserted': inserted}
