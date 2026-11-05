import json
import uuid

from football.engine import forecast, scores
from football.models import Match, instant, utc_now


class FootballStore:
    def __init__(self, store):
        self.store = store

    def matches(self, synthetic=False):
        with self.store.connect() as connection:
            rows = connection.execute('SELECT * FROM football_matches WHERE synthetic=? ORDER BY kickoff,match_id LIMIT 10001', (synthetic,)).fetchall()
        if len(rows) > 10000:
            raise ValueError('Archivio calcio oltre il limite di 10.000 partite')
        return [Match(row['match_id'], row['season'], row['kickoff'], row['home'], row['away'], row['status'],
                      row['home_goals'], row['away_goals'], row['available_at'], bool(row['synthetic']), row['source']) for row in rows]

    def upsert(self, records, synthetic=False):
        if not isinstance(records, list) or not 1 <= len(records) <= 10000:
            raise ValueError('Importare da 1 a 10.000 partite')
        matches = [Match.parse(row, synthetic) for row in records]
        inserted = updated = duplicates = 0
        with self.store.batch():
            for match in matches:
                with self.store.connect() as connection:
                    self.store.begin_write(connection)
                    old = connection.execute('SELECT * FROM football_matches WHERE match_id=? AND synthetic=?', (match.id, synthetic)).fetchone()
                    if old:
                        if (old['home'], old['away'], old['season']) != (match.home, match.away, match.season):
                            raise ValueError('Identificativo partita già associato a squadre o stagione diverse')
                        if old['status'] == 'FINISHED':
                            if (match.status, match.kickoff, match.home_goals, match.away_goals) != ('FINISHED', old['kickoff'], old['home_goals'], old['away_goals']):
                                raise ValueError('Risultato finale in conflitto: nessuna sovrascrittura')
                            duplicates += 1
                            continue
                        if (old['status'], old['kickoff']) == (match.status, match.kickoff):
                            duplicates += 1
                            continue
                        connection.execute('UPDATE football_matches SET kickoff=?,status=?,home_goals=?,away_goals=?,available_at=?,source=?,updated_at=? WHERE match_id=? AND synthetic=?',
                                           (match.kickoff, match.status, match.home_goals, match.away_goals, match.available_at, match.source, utc_now().isoformat(), match.id, synthetic))
                        updated += 1
                    else:
                        duplicate = connection.execute('SELECT match_id FROM football_matches WHERE synthetic=? AND season=? AND home=? AND away=?', (synthetic, match.season, match.home, match.away)).fetchone()
                        if duplicate:
                            raise ValueError('Partita già presente con un identificativo diverso')
                        connection.execute('INSERT INTO football_matches VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                           (match.id, synthetic, match.season, match.kickoff, match.home, match.away, match.status,
                                            match.home_goals, match.away_goals, match.available_at, match.source, utc_now().isoformat()))
                        inserted += 1
                    if match.status == 'FINISHED':
                        predictions = connection.execute('SELECT * FROM football_predictions WHERE match_id=? AND synthetic=?', (match.id, synthetic)).fetchall()
                        for prediction in predictions:
                            payload = json.loads(prediction['payload'])
                            if instant(prediction['created_at']) >= instant(match.kickoff) or payload['target']['kickoff'] != match.kickoff:
                                continue
                            evaluation = scores(payload['probabilities'], match.outcome)
                            connection.execute('INSERT INTO football_evaluations VALUES(?,?,?,?) ON CONFLICT DO NOTHING',
                                               (prediction['id'], utc_now().isoformat(), match.outcome, json.dumps(evaluation)))
        return {'inserted': inserted, 'updated': updated, 'duplicates': duplicates}

    def predict(self, match_id, synthetic=False):
        with self.store.batch():
            with self.store.connect() as connection:
                self.store.begin_write(connection)
                matches = self.matches(synthetic)
                target = next((m for m in matches if m.id == match_id), None)
                now = utc_now()
                if target is None or target.status != 'SCHEDULED' or instant(target.kickoff) <= now:
                    raise ValueError('Scegliere una partita programmata con calcio d’inizio futuro')
                payload = {**forecast(matches, target, now), 'target': target.payload(), 'synthetic': synthetic}
                identifier = str(uuid.uuid4())
                connection.execute('INSERT INTO football_predictions VALUES(?,?,?,?,?)',
                                   (identifier, target.id, synthetic, now.isoformat(), json.dumps(payload, allow_nan=False)))
        return {'id': identifier, 'created_at': now.isoformat(), **payload}

    def predictions(self, synthetic=False):
        with self.store.connect() as connection:
            rows = connection.execute('SELECT p.*,e.outcome,e.payload AS evaluation FROM football_predictions p LEFT JOIN football_evaluations e ON p.id=e.prediction_id WHERE p.synthetic=? ORDER BY p.created_at DESC LIMIT 100', (synthetic,)).fetchall()
        return [{'id': row['id'], 'created_at': row['created_at'], **json.loads(row['payload']),
                 'evaluation': {'outcome': row['outcome'], **json.loads(row['evaluation'])} if row['evaluation'] else None} for row in rows]

    def save_report(self, result, synthetic):
        identifier = str(uuid.uuid4())
        with self.store.connect() as connection:
            connection.execute('INSERT INTO football_reports VALUES(?,?,?,?)', (identifier, utc_now().isoformat(), synthetic, json.dumps(result, allow_nan=False)))
        return {'id': identifier, **result}

    def reports(self, synthetic):
        with self.store.connect() as connection:
            rows = connection.execute('SELECT * FROM football_reports WHERE synthetic=? ORDER BY created_at DESC LIMIT 10', (synthetic,)).fetchall()
        return [{'id': row['id'], 'created_at': row['created_at'], **json.loads(row['payload'])} for row in rows]
