"""Confronti prospettici appaiati, conservati nelle previsioni immutabili esistenti."""
from datetime import datetime, time, timezone
import hashlib
import json
import uuid
from zoneinfo import ZoneInfo

from predictions.engine import generate, save_prediction

ROME = ZoneInfo('Europe/Rome')
MARKER = 'prospective_comparison_v1'


def utc_now():
    return datetime.now(timezone.utc)


def validate_day(day):
    if day <= utc_now().astimezone(ROME).date():
        raise ValueError('Registrare il confronto entro il giorno precedente al concorso: scegliere una data futura')
    return datetime.combine(day, time.min, ROME)


def _rows(store, wheel, synthetic, target_id=None):
    query = 'SELECT p.*,r.matches,d.numbers AS actual_numbers FROM predictions p LEFT JOIN prediction_results r ON p.id=r.prediction_id LEFT JOIN draws d ON d.id=r.draw_row_id WHERE p.game=? AND p.variant=? AND p.wheel=? AND p.synthetic=?'
    query += ' AND p.payload LIKE ?'
    params = ['Lotto', 'ordinario', wheel, synthetic, '%"'+MARKER+'"%']
    if target_id is not None:
        query += ' AND p.target_id=?'
        params.append(target_id)
    query += ' ORDER BY p.created_at DESC,p.id LIMIT 2000'
    with store.connect() as connection:
        rows = connection.execute(query, params).fetchall()
    result = []
    for row in rows:
        payload = json.loads(row['payload'])
        if payload.get(MARKER):
            result.append({**dict(row), 'payload': payload,
                           'matches': json.loads(row['matches']) if row['matches'] is not None else None,
                           'actual_numbers': json.loads(row['actual_numbers']) if row['actual_numbers'] is not None else None})
    return result


def _pair(rows, identifier):
    arms = {row['payload'][MARKER]['arm']: row for row in rows if row['payload'][MARKER]['trial_id'] == identifier}
    if set(arms) != {'model', 'random'}:
        return None
    model, random = arms['model'], arms['random']
    marker = model['payload'][MARKER]
    target_day = datetime.fromisoformat(model['target_date']).astimezone(ROME).date()
    registered_before = all(datetime.fromisoformat(row['created_at']).astimezone(ROME).date() < target_day for row in arms.values())
    comparable = (registered_before and model['target_id'] == random['target_id'] and model['target_date'] == random['target_date']
                  and len(model['payload']['tickets']) == len(random['payload']['tickets']) == marker['protocol']['combinations']
                  and model['payload'].get('ticket_strategy','weighted') == random['payload'].get('ticket_strategy','weighted')
                  and model['payload']['training_sha256'] == random['payload']['training_sha256']
                  and model['payload']['rules_sha256'] == random['payload']['rules_sha256']
                  and random['payload'][MARKER]['protocol_sha256'] == marker['protocol_sha256'])
    evaluated = comparable and all(row['matches'] is not None for row in arms.values()) and model['actual_numbers'] == random['actual_numbers']
    return {'id': identifier, 'protocol_sha256': marker['protocol_sha256'], 'protocol': marker['protocol'],
            'target_id': model['target_id'], 'target_day': target_day.isoformat(), 'synthetic': bool(model['synthetic']),
            'status': 'evaluated' if evaluated else 'awaiting_result' if comparable else 'not_comparable',
            'registered_before_day': registered_before, 'actual_numbers': model['actual_numbers'],
            'model': {key: model[key] for key in ('id', 'created_at', 'payload', 'matches')},
            'random': {key: random[key] for key in ('id', 'created_at', 'payload', 'matches')}}


def _existing(rows, fingerprint):
    for row in rows:
        if row['payload'][MARKER]['protocol_sha256'] == fingerprint:
            paired = _pair(rows, row['payload'][MARKER]['trial_id'])
            if paired is None:
                raise ValueError('Confronto incompleto già presente: verificare il database')
            return {**paired, 'already_registered': True}
    return None


def register_trial(store, history, day, model='frequency', combinations=5, seed=42, ticket_strategy='weighted', history_limit=500):
    target_date = validate_day(day)
    if not history or any((draw.game, draw.variant, draw.wheel, draw.synthetic) != ('Lotto', 'ordinario', history[0].wheel, history[0].synthetic) for draw in history):
        raise ValueError('Il confronto futuro richiede una sola ruota Lotto ordinario')
    wheel, synthetic = history[0].wheel, history[0].synthetic
    protocol = {'version': 1, 'game': 'Lotto', 'variant': 'ordinario', 'wheel': wheel, 'model': model,
                'combinations': combinations, 'seed': seed, 'ticket_strategy': ticket_strategy, 'history_limit': history_limit, 'synthetic': synthetic,
                'primary_metric': 'at_least_two_matches_per_draw', 'baseline': 'uniform',
                'generator_version': '1' if ticket_strategy == 'weighted' else '2-disjoint',
                'rules_sha256': hashlib.sha256(json.dumps(store.rules.rules[('Lotto','ordinario')], sort_keys=True).encode()).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    target_id = 'lotto:' + day.isoformat()
    previous = _existing(_rows(store, wheel, synthetic, target_id), fingerprint)
    if previous is not None:
        return previous
    trial_id = str(uuid.uuid4())
    baseline_seed = int.from_bytes(hashlib.sha256(f'prospective:{seed}:random:{wheel}:{day.isoformat()}'.encode()).digest()[:4], 'little')
    generated = {'model': generate(history, store.rules, model, combinations, seed, ticket_strategy),
                 'random': generate(history, store.rules, 'uniform', combinations, baseline_seed, ticket_strategy)}
    with store.batch():
        with store.connect() as connection:
            store.begin_write(connection)
        previous = _existing(_rows(store, wheel, synthetic, target_id), fingerprint)
        if previous is not None:
            return previous
        for arm, result in generated.items():
            result[MARKER] = {'trial_id': trial_id, 'protocol_sha256': fingerprint, 'protocol': protocol, 'arm': arm}
            save_prediction(store, result, target_id, target_date)
    result = _pair(_rows(store, wheel, synthetic, target_id), trial_id)
    if result is None:
        raise ValueError('Confronto non disponibile dopo il salvataggio')
    return {**result, 'already_registered': False}


def list_trials(store, wheel, synthetic=False):
    rows = _rows(store, wheel, synthetic)
    identifiers = list(dict.fromkeys(row['payload'][MARKER]['trial_id'] for row in rows))
    pairs = [_pair(rows, identifier) for identifier in identifiers]
    trials = [pair for pair in pairs if pair is not None]
    summaries = []
    for fingerprint in dict.fromkeys(row['protocol_sha256'] for row in trials):
        group = [row for row in trials if row['protocol_sha256'] == fingerprint]
        scored = [row for row in group if row['status'] == 'evaluated']
        totals = {}
        for arm in ('model', 'random'):
            matches = [value for row in scored for value in row[arm]['matches']]
            totals[arm] = {'draws_at_least_two': sum(max(row[arm]['matches']) >= 2 for row in scored),
                           'mean_matches': sum(matches) / len(matches) if matches else None}
        summaries.append({'protocol_sha256': fingerprint, 'protocol': group[0]['protocol'], 'registered': len(group),
                          'evaluated': len(scored), 'awaiting': sum(row['status'] == 'awaiting_result' for row in group), **totals})
    return {'trials': trials, 'summaries': summaries, 'incomplete_pairs': len(identifiers) - len(trials), 'row_limit': 2000,
            'notes': 'Confronti registrati prima del giorno del concorso. Raggruppamento per protocollo fisso, senza mescolare modelli, seed o budget. '
                     'Metrica primaria: concorsi con almeno due corrispondenze. Nessuna prova automatica di vantaggio, indipendenza o redditività. '
                     'Provare molti protocolli e scegliere dopo il migliore richiede una nuova verifica indipendente.'}
