"""Prova funzionale con quattro concorsi reali, solo in un database temporaneo.

Servizi pubblici individuati negli script collegati alla pagina ufficiale:
https://www.lotto-italia.it/lotto/estratti-ruote
Non abilita il connettore automatico e non scrive negli archivi dell'utente.
"""
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import ssl
import sys
import tempfile
from unittest.mock import patch
from urllib.request import HTTPSHandler, Request, build_opener
from zoneinfo import ZoneInfo

# Allow invocation from the project root with `python scripts/...py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_sources.importer import import_content
from data_sources.lotto_official import OfficialRedirect, WHEELS, check_url
from data_sources.preview import preview_content
from database.store import Store
from games.models import Draw
from games.rules import RuleRegistry
from lotto_statistics.engine import analyze
from predictions.engine import generate, save_prediction

BASE = 'https://www.lotto-italia.it/gdl/estrazioni-e-vincite/'
ROME = ZoneInfo('Europe/Rome')


def post(name, body):
    url = BASE + name
    check_url(url)
    request = Request(url, data=json.dumps(body).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'User-Agent': 'LottoPredictAI/0.1 (functional validation)'})
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), OfficialRedirect())
    with opener.open(request, timeout=30) as response:
        check_url(response.geturl())
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError('Risposta ufficiale troppo grande')
    return json.loads(content), hashlib.sha256(content).hexdigest()


def sample_dates(today):
    result = set()
    month = today.replace(day=1)
    for _ in range(2):
        days, _ = post('calendario-estrazioni-del-lotto.json', {'anno': str(month.year), 'mese': f'{month.month:02d}'})
        if not isinstance(days, list) or any(type(day) is not int or not 1 <= day <= 31 for day in days):
            raise ValueError('Formato del calendario ufficiale cambiato')
        result.update(date(month.year, month.month, day) for day in days if date(month.year, month.month, day) < today)
        if len(result) >= 4:
            return sorted(result)[-4:]
        month = (month - timedelta(days=1)).replace(day=1)
    raise ValueError('Meno di quattro concorsi recenti disponibili')


def extraction(day, registry):
    payload, digest = post('estrazioni-del-lotto.json', {'data': day.strftime('%Y%m%d')})
    if payload.get('esito') != 'OK' or type(payload.get('data')) is not int:
        raise ValueError('Risultato ufficiale non disponibile')
    reference = datetime.fromtimestamp(payload['data'] / 1000, ROME)
    if reference.date() != day:
        raise ValueError('La fonte ha restituito una data diversa da quella richiesta')
    rows = payload.get('estrazione')
    if not isinstance(rows, list) or len(rows) != 11:
        raise ValueError('Concorso incompleto')
    draws = []
    for row in rows:
        wheel = WHEELS.get(row.get('ruota'))
        numbers = row.get('numeri')
        if wheel is None or not isinstance(numbers, list):
            raise ValueError('Formato ruota o numeri non riconosciuto')
        # Midnight is a date reference, never an observed extraction time.
        draw = Draw('Lotto', 'ordinario', 'lotto:' + day.isoformat(),
                    datetime(day.year, day.month, day.day, tzinfo=ROME), tuple(numbers), wheel,
                    source=BASE + 'estrazioni-del-lotto.json', date_precision='date')
        registry.validate(draw)
        draws.append(draw)
    if {draw.wheel for draw in draws} != set(registry.rules[('Lotto', 'ordinario')]['wheels']):
        raise ValueError('Ruote duplicate o mancanti')
    return draws, digest


def content(draws):
    records = []
    for draw in draws:
        record = asdict(draw)
        record['occurred_at'] = draw.occurred_at.isoformat()
        records.append(record)
    return json.dumps(records).encode()


def main():
    registry = RuleRegistry()
    days = sample_dates(datetime.now(ROME).date())
    all_draws, digests = [], {}
    for day in days:
        draws, digest = extraction(day, registry)
        all_draws.extend(draws)
        digests[day.isoformat()] = digest
    training = [draw for draw in all_draws if draw.occurred_at.date() < days[-1]]
    targets = [draw for draw in all_draws if draw.occurred_at.date() == days[-1]]
    with tempfile.TemporaryDirectory(prefix='lottopredict-official-replay-') as folder:
        store = Store(Path(folder) / 'validation.sqlite3', registry)
        preview = preview_content(store, content(training), 'json')
        assert preview['new'] == 33 and store.count() == 0
        report = import_content(store, content(training), 'json', BASE + 'estrazioni-del-lotto.json')
        assert report.inserted == 33 and report.rejected == 0
        history = store.history('Lotto', 'ordinario', 'Roma', False, 1000)
        analysis = analyze(history, registry)
        assert analysis['draws'] == 3 and not analysis['synthetic']
        generated = generate(history, registry, combinations=2)
        target = next(draw for draw in targets if draw.wheel == 'Roma')
        issued = target.occurred_at - timedelta(hours=12)
        # Historical replay only. Both clocks are patched exclusively inside this temporary database.
        with patch('predictions.engine.datetime', wraps=datetime) as prediction_clock, patch('database.store.datetime', wraps=datetime) as store_clock:
            prediction_clock.now.return_value = issued
            store_clock.now.return_value = issued
            identifier = save_prediction(store, generated, target.draw_id, target.occurred_at)
        report = import_content(store, content(targets), 'json', BASE + 'estrazioni-del-lotto.json')
        assert report.inserted == 11 and report.rejected == 0
        saved = store.prediction_history()
        assert len(saved) == 1 and saved[0]['matches'] is not None
        actual_matches = [len(set(ticket['numbers']) & set(target.numbers)) for ticket in generated['tickets']]
        assert json.loads(saved[0]['matches']) == actual_matches
        with store.connect() as connection:
            try:
                connection.execute('DELETE FROM predictions WHERE id=?', (identifier,))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('Previsione cancellabile')
        duplicate = import_content(store, content(all_draws), 'json', BASE + 'estrazioni-del-lotto.json')
        assert duplicate.duplicates == 44 and duplicate.inserted == 0 and store.count(True) == 0
        reopened = Store(store.path, registry)
        assert reopened.count() == 44 and reopened.prediction_history()[0]['matches'] is not None
    print(json.dumps({'status': 'ok', 'scope': 'functional_historical_replay_not_prospective_validation',
                      'source': BASE + 'estrazioni-del-lotto.json', 'dates': [day.isoformat() for day in days],
                      'real_draws': 44, 'training_per_wheel': 3, 'target_wheels': 11,
                      'source_response_sha256': digests,
                      'checks': ['preview', 'import', 'analysis', 'generation', 'historical_replay_evaluation',
                                 'immutability', 'duplicates', 'synthetic_separation', 'database_reopen'],
                      'automatic_sync_enabled': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
