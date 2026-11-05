import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

import numpy as np
from football.models import instant


def read_upload(content, format, synthetic):
    if len(content) > 5 * 1024 * 1024:
        raise ValueError('File calcio oltre 5 MiB')
    from data_sources.importer import unique_fields
    if format == 'json':
        return json.loads(content.decode('utf-8-sig'), object_pairs_hook=unique_fields)
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('Intestazioni CSV mancanti o duplicate')
    result = []
    for row in reader:
        if None in row:
            raise ValueError('CSV con colonne oltre le intestazioni')
        for key in ('season', 'home_goals', 'away_goals'):
            if key in row:
                row[key] = int(row[key]) if row[key] else None
        if 'available_at' in row and not row['available_at']:
            row['available_at'] = None
        if 'synthetic' in row:
            if row['synthetic'] not in ('true', 'false'):
                raise ValueError('synthetic deve essere true o false')
            row['synthetic'] = row['synthetic'] == 'true'
        result.append(row)
        if len(result) > 10000:
            raise ValueError('Massimo 10.000 partite per importazione')
    return result


def demo():
    rng = np.random.default_rng(42)
    teams = [f'Squadra {chr(65 + i)}' for i in range(8)]
    start = (datetime.now(timezone.utc) - timedelta(days=400)).replace(hour=15, minute=0, second=0, microsecond=0)
    records = []
    for season in range(2023, 2026):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                index = len(records)
                kickoff = start + timedelta(days=2 * index)
                records.append({'id': f'demo:{season}:{home}:{away}', 'season': season, 'kickoff': kickoff.isoformat(),
                                'home': home, 'away': away, 'status': 'FINISHED',
                                'home_goals': int(rng.poisson(1.5)), 'away_goals': int(rng.poisson(1.1)),
                                'available_at': (kickoff + timedelta(hours=3)).isoformat(),
                                'synthetic': True, 'source': 'demo artificiale seed 42'})
    # Stable identifiers; future dates are created only on the first demo import.
    for i in range(4):
        records.append({'id': f'demo:future:{i}', 'season': 2026,
                        'kickoff': (start + timedelta(days=405+i)).isoformat(),
                        'home': teams[2*i], 'away': teams[2*i+1], 'status': 'SCHEDULED',
                        'synthetic': True, 'source': 'demo artificiale seed 42'})
    return records


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirect della fonte calcio rifiutato')


def fetch_season(season):
    token = os.environ.get('FOOTBALL_DATA_API_TOKEN')
    if os.environ.get('FOOTBALL_DATA_ENABLED') != 'true' or not token:
        raise ValueError('Fonte automatica non configurata: abilitare FOOTBALL_DATA_ENABLED e impostare FOOTBALL_DATA_API_TOKEN nel server')
    url = f'https://api.football-data.org/v4/competitions/SA/matches?season={season}'
    request = Request(url, headers={'X-Auth-Token': token, 'User-Agent': 'LottoPredictAI football research'})
    try:
        opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        with opener.open(request, timeout=30) as response:
            content = response.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise ValueError('Risposta calcio oltre 5 MiB')
    except HTTPError as error:
        raise ValueError(f'Fonte calcio non disponibile (HTTP {error.code}): verificare piano, token e limiti') from None
    except URLError:
        raise ValueError('Fonte calcio non raggiungibile: verificare rete e TLS del server') from None
    payload = json.loads(content)
    if not isinstance(payload, dict) or payload.get('competition', {}).get('code') != 'SA' or not isinstance(payload.get('matches'), list) or not payload['matches']:
        raise ValueError('Risposta della fonte calcio non riconosciuta o vuota')
    records = []
    statuses = {'TIMED': 'SCHEDULED', 'SCHEDULED': 'SCHEDULED', 'FINISHED': 'FINISHED',
                'POSTPONED': 'POSTPONED', 'CANCELLED': 'CANCELLED', 'SUSPENDED': 'POSTPONED',
                'IN_PLAY': 'POSTPONED', 'PAUSED': 'POSTPONED', 'AWARDED': 'CANCELLED'}
    for item in payload['matches']:
        status = statuses.get(item.get('status'))
        if status is None or item.get('season', {}).get('startDate', '')[:4] != str(season):
            raise ValueError('Stagione o stato della fonte non riconosciuti')
        result = {'id': 'fd:' + str(item['id']), 'season': season, 'kickoff': instant(item['utcDate']).isoformat(),
                  'home': item['homeTeam']['name'], 'away': item['awayTeam']['name'], 'status': status,
                  'synthetic': False, 'source': 'football-data.org / Serie A'}
        if status == 'FINISHED':
            score = item.get('score', {})
            if score.get('duration') != 'REGULAR':
                raise ValueError('Sono supportati solo risultati al termine dei tempi regolamentari')
            result.update(home_goals=score['fullTime']['home'], away_goals=score['fullTime']['away'],
                          available_at=instant(item['lastUpdated']).isoformat())
        records.append(result)
    return records
