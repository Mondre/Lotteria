from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Data e ora con fuso obbligatori')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Match:
    id: str
    season: int
    kickoff: str
    home: str
    away: str
    status: str
    home_goals: int | None = None
    away_goals: int | None = None
    available_at: str | None = None
    synthetic: bool = False
    source: str = 'importazione'

    @classmethod
    def parse(cls, record, synthetic):
        required = {'id', 'season', 'kickoff', 'home', 'away', 'status'}
        if not isinstance(record, dict) or not required.issubset(record) or set(record) - set(cls.__dataclass_fields__):
            raise ValueError('Campi della partita mancanti o sconosciuti')
        if type(synthetic) is not bool or type(record.get('synthetic', synthetic)) is not bool or record.get('synthetic', synthetic) != synthetic:
            raise ValueError('Dati reali e sintetici devono restare separati')
        item = dict(record, synthetic=synthetic)
        for name in ('id', 'home', 'away', 'source'):
            value = item.get(name, 'importazione' if name == 'source' else '')
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
                raise ValueError(f'{name}: testo obbligatorio, massimo 200 caratteri')
            item[name] = value.strip()
        if item['home'].casefold() == item['away'].casefold():
            raise ValueError('Le squadre devono essere diverse')
        if type(item['season']) is not int or not 2000 <= item['season'] <= 2100:
            raise ValueError('Stagione: indicare l’anno iniziale, es. 2025')
        item['kickoff'] = instant(item['kickoff']).isoformat()
        if item['status'] not in ('SCHEDULED', 'FINISHED', 'POSTPONED', 'CANCELLED'):
            raise ValueError('Stato della partita non supportato')
        if item['status'] == 'FINISHED':
            if any(type(item.get(key)) is not int or not 0 <= item[key] <= 20 for key in ('home_goals', 'away_goals')):
                raise ValueError('Risultato finale: gol interi da 0 a 20')
            if not item.get('available_at'):
                raise ValueError('Risultato finale: available_at con fuso obbligatorio')
            item['available_at'] = instant(item['available_at']).isoformat()
            if not instant(item['kickoff']) < instant(item['available_at']) <= utc_now():
                raise ValueError('Disponibilità del risultato precedente al calcio d’inizio o futura')
        elif any(item.get(key) is not None for key in ('home_goals', 'away_goals', 'available_at')):
            raise ValueError('Una partita non terminata non deve avere un risultato')
        return cls(**item)

    def payload(self):
        return asdict(self)

    @property
    def outcome(self):
        return '1' if self.home_goals > self.away_goals else '2' if self.home_goals < self.away_goals else 'X'
