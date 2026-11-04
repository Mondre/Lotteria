import json
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from games.models import Draw
from games.rules import RuleRegistry

_ACTIVE_CONNECTION = ContextVar("lottopredict_connection", default=None)

SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    id INTEGER PRIMARY KEY,
    game TEXT NOT NULL, variant TEXT NOT NULL, wheel TEXT NOT NULL,
    draw_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
    numbers TEXT NOT NULL, extras TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)), source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(game, variant, wheel, draw_id, synthetic)
);
CREATE INDEX IF NOT EXISTS draws_chronological
ON draws(game, variant, wheel, synthetic, occurred_at);
CREATE TABLE IF NOT EXISTS update_log (
    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
    level TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
    game TEXT NOT NULL, variant TEXT NOT NULL, wheel TEXT NOT NULL,
    synthetic INTEGER NOT NULL, target_id TEXT NOT NULL, target_date TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id TEXT PRIMARY KEY REFERENCES predictions(id),
    draw_row_id INTEGER NOT NULL REFERENCES draws(id), evaluated_at TEXT NOT NULL,
    matches TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS predictions_immutable_update BEFORE UPDATE ON predictions
BEGIN SELECT RAISE(ABORT, 'Previsione immutabile'); END;
CREATE TRIGGER IF NOT EXISTS predictions_immutable_delete BEFORE DELETE ON predictions
BEGIN SELECT RAISE(ABORT, 'Previsione immutabile'); END;
CREATE TRIGGER IF NOT EXISTS results_immutable_update BEFORE UPDATE ON prediction_results
BEGIN SELECT RAISE(ABORT, 'Risultato immutabile'); END;
CREATE TRIGGER IF NOT EXISTS results_immutable_delete BEFORE DELETE ON prediction_results
BEGIN SELECT RAISE(ABORT, 'Risultato immutabile'); END;
PRAGMA user_version = 2;
"""


class Store:
    backend = "sqlite"

    def __init__(self, path: Path, rules: RuleRegistry):
        self.path = path
        self.rules = rules
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Versione database non supportata")
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        active = self.active_connection()
        if active is not None:
            yield active
            return
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def add_draw(self, draw: Draw) -> bool:
        self.rules.validate(draw)
        with self.connect() as connection:
            self.begin_write(connection)
            existing = connection.execute(
                "SELECT * FROM draws WHERE game=? AND variant=? AND wheel=? AND draw_id=? AND synthetic=?",
                (draw.game, draw.variant, draw.wheel, draw.draw_id, draw.synthetic),
            ).fetchone()
            if existing:
                same = self.same_content(self.from_row(existing), draw)
                if not same:
                    raise ValueError("Identificativo esistente con contenuto diverso: nessuna sovrascrittura")
                return False
            cursor = connection.execute(
                "INSERT INTO draws(game,variant,wheel,draw_id,occurred_at,numbers,extras,synthetic,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id",
                (draw.game, draw.variant, draw.wheel, draw.draw_id,
                 draw.occurred_at.astimezone(timezone.utc).isoformat(),
                 json.dumps(draw.numbers), json.dumps(draw.extras), draw.synthetic,
                 draw.source, datetime.now(timezone.utc).isoformat()),
            )
            draw_row_id = cursor.fetchone()["id"]
            connection.execute("INSERT INTO update_log(created_at,level,message) VALUES(?,?,?)",
                               (datetime.now(timezone.utc).isoformat(), "INFO",
                                f"Estrazione aggiunta: {draw.game}/{draw.variant}/{draw.draw_id}"))
            self.evaluate_predictions(connection, draw, draw_row_id)
        return True

    def list_draws(self, game: str | None = None, synthetic: bool = False, limit: int = 1000) -> list[sqlite3.Row]:
        if not 1 <= limit <= 100000:
            raise ValueError("Limite non valido")
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM draws WHERE synthetic=? AND (CAST(? AS TEXT) IS NULL OR game=?) ORDER BY occurred_at DESC, id DESC LIMIT ?",
                (synthetic, game, game, limit),
            ).fetchall()

    def count(self, synthetic: bool = False) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT COUNT(*) AS total FROM draws WHERE synthetic=?", (synthetic,)).fetchone()["total"]

    def recent_logs(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM update_log ORDER BY id DESC LIMIT 100").fetchall()

    def log(self, level: str, message: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO update_log(created_at,level,message) VALUES(?,?,?)",
                               (datetime.now(timezone.utc).isoformat(), level, message))

    def history(self, game: str, variant: str, wheel: str = "", synthetic: bool = False,
                limit: int = 1000) -> list[Draw]:
        if not 1 <= limit <= 100000:
            raise ValueError("Limite non valido")
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM draws WHERE game=? AND variant=? AND wheel=? AND synthetic=? "
                "ORDER BY occurred_at DESC,id DESC LIMIT ?", (game, variant, wheel, synthetic, limit),
            ).fetchall()
        return [self.from_row(row) for row in reversed(rows)]

    @staticmethod
    def from_row(row) -> Draw:
        return Draw(row["game"], row["variant"], row["draw_id"],
                    datetime.fromisoformat(row["occurred_at"]), tuple(json.loads(row["numbers"])),
                    row["wheel"], json.loads(row["extras"]), bool(row["synthetic"]), row["source"])

    @staticmethod
    def same_content(left: Draw, right: Draw) -> bool:
        return left.occurred_at == right.occurred_at and left.numbers == right.numbers and left.extras == right.extras

    def existing_draws(self, draws: list[Draw]) -> dict[tuple, Draw]:
        """Lookup in blocchi compatibili con SQLite e PostgreSQL, senza scritture."""
        grouped = {}
        for draw in draws:
            grouped.setdefault(draw.synthetic, set()).add((draw.game, draw.variant, draw.wheel, draw.draw_id))
        found = {}
        with self.connect() as connection:
            for synthetic, keys in grouped.items():
                keys = sorted(keys)
                for offset in range(0, len(keys), 200):
                    batch = keys[offset:offset + 200]
                    placeholders = ",".join("(?,?,?,?)" for _ in batch)
                    query = "SELECT * FROM draws WHERE synthetic=? AND (game,variant,wheel,draw_id) IN (" + placeholders + ")"
                    parameters = [synthetic] + [value for key in batch for value in key]
                    for row in connection.execute(query, parameters).fetchall():
                        draw = self.from_row(row)
                        found[(draw.game, draw.variant, draw.wheel, draw.draw_id, draw.synthetic)] = draw
        return found

    def save_prediction(self, payload: dict, target_id: str, target_date: datetime) -> str:
        import uuid
        created_at = datetime.now(timezone.utc)
        if not target_id.strip() or target_date.tzinfo is None or target_date <= created_at:
            raise ValueError("La previsione richiede una data futura con fuso e un identificativo")
        train_end = datetime.fromisoformat(payload["train_end"])
        if train_end.tzinfo is None or train_end > created_at or train_end >= target_date:
            raise ValueError("Data finale di training non valida")
        if not payload["tickets"]:
            raise ValueError("Nessuna combinazione")
        rule = self.rules.rules[(payload["game"], payload["variant"])]
        for ticket in payload["tickets"]:
            numbers = ticket["numbers"]
            if (len(numbers) != rule["count"] or len(set(numbers)) != len(numbers)
                    or any(type(number) is not int or not rule["minimum"] <= number <= rule["maximum"] for number in numbers)):
                raise ValueError("Combinazione non valida")
        if (rule["wheels"] and payload["wheel"] not in rule["wheels"]) or (not rule["wheels"] and payload["wheel"]):
            raise ValueError("Ruota non valida")
        identifier = str(uuid.uuid4())
        with self.connect() as connection:
            self.begin_write(connection)
            existing = connection.execute("SELECT 1 FROM draws WHERE game=? AND variant=? AND wheel=? AND draw_id=? AND synthetic=?",
                                          (payload["game"], payload["variant"], payload["wheel"], target_id, payload["synthetic"])).fetchone()
            if existing:
                raise ValueError("Il risultato dell'estrazione è già presente")
            connection.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?)",
                               (identifier, created_at.astimezone(timezone.utc).isoformat(), payload["game"], payload["variant"],
                                payload["wheel"], payload["synthetic"], target_id,
                                target_date.astimezone(timezone.utc).isoformat(), json.dumps(payload, allow_nan=False)))
        return identifier

    @staticmethod
    def evaluate_predictions(connection, draw: Draw, draw_row_id: int) -> None:
        rows = connection.execute("SELECT * FROM predictions WHERE game=? AND variant=? AND wheel=? AND target_id=? AND synthetic=?",
                                  (draw.game, draw.variant, draw.wheel, draw.draw_id, draw.synthetic)).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            if (datetime.fromisoformat(row["created_at"]) >= draw.occurred_at
                    or datetime.fromisoformat(payload["train_end"]) >= draw.occurred_at
                    or datetime.fromisoformat(row["target_date"]) != draw.occurred_at):
                continue
            matches = [len(set(ticket["numbers"]) & set(draw.numbers)) for ticket in payload["tickets"]]
            connection.execute("INSERT INTO prediction_results VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                               (row["id"], draw_row_id, datetime.now(timezone.utc).isoformat(), json.dumps(matches)))

    def prediction_history(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT p.*,r.matches FROM predictions p LEFT JOIN prediction_results r "
                                      "ON p.id=r.prediction_id ORDER BY p.created_at DESC LIMIT 1000").fetchall()
        return [dict(row) for row in rows]

    def begin_write(self, connection) -> None:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")

    def active_connection(self):
        active = _ACTIVE_CONNECTION.get()
        return active[1] if active and active[0] is self else None

    @contextmanager
    def batch(self):
        """Riusa una transazione durante l'importazione, evitando un commit per riga."""
        with self.connect() as connection:
            self.begin_write(connection)
            token = _ACTIVE_CONNECTION.set((self, connection))
            try:
                yield
            finally:
                _ACTIVE_CONNECTION.reset(token)

    def close(self) -> None:
        """SQLite apre connessioni solo per la durata delle singole operazioni."""
