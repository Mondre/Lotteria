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
    date_precision TEXT NOT NULL DEFAULT 'instant',
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
CREATE TABLE IF NOT EXISTS source_updates (
    source_key TEXT PRIMARY KEY, checked_at TEXT NOT NULL, details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY, operation TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, finished_at TEXT NOT NULL, parameters TEXT NOT NULL,
    result TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS experiments_created ON experiments(created_at,id);
CREATE TABLE IF NOT EXISTS football_matches (
    match_id TEXT NOT NULL, synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)), season INTEGER NOT NULL,
    kickoff TEXT NOT NULL, home TEXT NOT NULL, away TEXT NOT NULL, status TEXT NOT NULL,
    home_goals INTEGER, away_goals INTEGER, available_at TEXT, source TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(match_id,synthetic), UNIQUE(synthetic,season,home,away)
);
CREATE INDEX IF NOT EXISTS football_chronological ON football_matches(synthetic,kickoff);
CREATE TABLE IF NOT EXISTS football_predictions (
    id TEXT PRIMARY KEY, match_id TEXT NOT NULL, synthetic INTEGER NOT NULL,
    created_at TEXT NOT NULL, payload TEXT NOT NULL,
    FOREIGN KEY(match_id,synthetic) REFERENCES football_matches(match_id,synthetic)
);
CREATE TABLE IF NOT EXISTS football_evaluations (
    prediction_id TEXT PRIMARY KEY REFERENCES football_predictions(id), evaluated_at TEXT NOT NULL,
    outcome TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS football_reports (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, synthetic INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS football_predictions_update BEFORE UPDATE ON football_predictions
BEGIN SELECT RAISE(ABORT, 'Previsione calcio immutabile'); END;
CREATE TRIGGER IF NOT EXISTS football_predictions_delete BEFORE DELETE ON football_predictions
BEGIN SELECT RAISE(ABORT, 'Previsione calcio immutabile'); END;
CREATE TRIGGER IF NOT EXISTS football_evaluations_update BEFORE UPDATE ON football_evaluations
BEGIN SELECT RAISE(ABORT, 'Risultato calcio immutabile'); END;
CREATE TRIGGER IF NOT EXISTS football_evaluations_delete BEFORE DELETE ON football_evaluations
BEGIN SELECT RAISE(ABORT, 'Risultato calcio immutabile'); END;
PRAGMA user_version = 4;
"""


class Store:
    backend = "sqlite"

    def __init__(self, path: Path, rules: RuleRegistry):
        self.path = path
        self.rules = rules
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4):
                raise ValueError("Versione database non supportata")
            columns = connection.execute("PRAGMA table_info(draws)").fetchall()
            if columns and "date_precision" not in {row["name"] for row in columns}:
                connection.execute("ALTER TABLE draws ADD COLUMN date_precision TEXT NOT NULL DEFAULT 'instant'")
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
                "INSERT INTO draws(game,variant,wheel,draw_id,occurred_at,numbers,extras,synthetic,source,created_at,date_precision) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
                (draw.game, draw.variant, draw.wheel, draw.draw_id,
                 draw.occurred_at.astimezone(timezone.utc).isoformat(),
                 json.dumps(draw.numbers), json.dumps(draw.extras), draw.synthetic,
                 draw.source, datetime.now(timezone.utc).isoformat(), draw.date_precision),
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
                    row["wheel"], json.loads(row["extras"]), bool(row["synthetic"]), row["source"], row["date_precision"])

    @staticmethod
    def same_content(left: Draw, right: Draw) -> bool:
        return (left.occurred_at == right.occurred_at and left.numbers == right.numbers
                and left.extras == right.extras and left.date_precision == right.date_precision)

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

    def history_by_ids(self, game: str, variant: str, wheel: str, identifiers: list[str], limit: int) -> list[Draw]:
        """Solo concorsi attestati dalla sincronizzazione: esclude copie manuali con altri ID."""
        if not 1 <= limit <= 10000 or len(identifiers) > 10000:
            raise ValueError("Finestra della fonte non valida")
        rows = []
        with self.connect() as connection:
            for offset in range(0, len(identifiers), 200):
                batch = identifiers[offset:offset + 200]
                query = ("SELECT * FROM draws WHERE game=? AND variant=? AND wheel=? AND synthetic=0 "
                         "AND draw_id IN (" + ",".join("?" for _ in batch) + ")")
                rows.extend(connection.execute(query, [game, variant, wheel, *batch]).fetchall())
        return sorted((self.from_row(row) for row in rows), key=lambda draw: (draw.occurred_at, draw.draw_id))[-limit:]

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
        from winforlife.engine import validate_tickets
        validate_tickets(payload, rule)
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
            target = datetime.fromisoformat(row["target_date"])
            if draw.date_precision == "date":
                from zoneinfo import ZoneInfo
                matches_date = target.astimezone(ZoneInfo("Europe/Rome")).date() == draw.occurred_at.astimezone(ZoneInfo("Europe/Rome")).date()
            else:
                matches_date = target == draw.occurred_at
            if (datetime.fromisoformat(row["created_at"]) >= draw.occurred_at
                    or datetime.fromisoformat(payload["train_end"]) >= draw.occurred_at
                    or not matches_date):
                continue
            matches = [len(set(ticket["numbers"]) & set(draw.numbers)) for ticket in payload["tickets"]]
            if payload.get("include_numerone"):
                matches = {"main_matches": matches,
                           "numerone_matches": [ticket["extras"]["numerone"] == draw.extras["numerone"] for ticket in payload["tickets"]],
                           "actual_numerone": draw.extras["numerone"]}
            connection.execute("INSERT INTO prediction_results VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                               (row["id"], draw_row_id, datetime.now(timezone.utc).isoformat(), json.dumps(matches)))

    def prediction_history(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT p.*,r.matches,d.occurred_at AS result_date,d.date_precision AS result_precision "
                                      "FROM predictions p LEFT JOIN prediction_results r ON p.id=r.prediction_id "
                                      "LEFT JOIN draws d ON d.game=p.game AND d.variant=p.variant AND d.wheel=p.wheel "
                                      "AND d.synthetic=p.synthetic AND d.draw_id=p.target_id "
                                      "ORDER BY p.created_at DESC LIMIT 1000").fetchall()
        result = []
        for raw in rows:
            row = dict(raw)
            if row["matches"] is not None:
                stored_matches = json.loads(row["matches"])
                if isinstance(stored_matches, dict) and "main_matches" in stored_matches:
                    row["winforlife_result"] = stored_matches
                    row["numerone_matches"] = stored_matches["numerone_matches"]
                    row["actual_numerone"] = stored_matches["actual_numerone"]
                    row["matches"] = json.dumps(stored_matches["main_matches"])
            if row["matches"] is not None:
                status = "evaluated"
            elif row["result_date"] is None:
                status = "awaiting"
            elif row["result_precision"] == "date":
                status = "unscorable_time"
            else:
                status = "unmatched"
            row["evaluation_status"] = status
            result.append(row)
        return result

    def sync_info(self, key: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM source_updates WHERE source_key=?", (key,)).fetchone()
        return {"checked_at": row["checked_at"], **json.loads(row["details"])} if row else None

    def save_sync_info(self, key: str, details: dict) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO source_updates(source_key,checked_at,details) VALUES(?,?,?) "
                               "ON CONFLICT(source_key) DO UPDATE SET checked_at=excluded.checked_at,details=excluded.details",
                               (key, datetime.now(timezone.utc).isoformat(), json.dumps(details, allow_nan=False)))

    def save_experiment(self, identifier: str, operation: str, status: str, parameters: dict,
                        created_at: str, result=None, error: str | None = None) -> None:
        if operation not in ("analyze", "generate", "backtest", "simulate") or status not in ("completed", "failed"):
            raise ValueError("Tipo o stato esperimento non valido")
        with self.connect() as connection:
            connection.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",
                               (identifier, operation, status, created_at, datetime.now(timezone.utc).isoformat(),
                                json.dumps(parameters, allow_nan=False),
                                json.dumps(result, allow_nan=False) if result is not None else None, error))

    @staticmethod
    def experiment_from_row(raw) -> dict:
        row = dict(raw)
        row["request"] = json.loads(row.pop("parameters"))
        if "result" in row:
            if row["result"] is not None:
                row["result"] = json.loads(row["result"])
            else:
                del row["result"]
        row["persisted"] = True
        return row

    def experiment(self, identifier: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM experiments WHERE id=?", (identifier,)).fetchone()
        return self.experiment_from_row(row) if row else None

    def list_experiments(self, limit: int = 30, offset: int = 0, operation: str | None = None) -> dict:
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("Paginazione non valida")
        if operation is not None and operation not in ("analyze", "generate", "backtest", "simulate"):
            raise ValueError("Tipo esperimento non valido")
        with self.connect() as connection:
            rows = connection.execute("SELECT id,operation,status,created_at,finished_at,parameters,error "
                                      "FROM experiments WHERE (CAST(? AS TEXT) IS NULL OR operation=?) "
                                      "ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                                      (operation, operation, limit, offset)).fetchall()
            total = connection.execute("SELECT COUNT(*) AS total FROM experiments "
                                       "WHERE (CAST(? AS TEXT) IS NULL OR operation=?)", (operation, operation)).fetchone()["total"]
        return {"items": [self.experiment_from_row(row) for row in rows], "total": total, "limit": limit, "offset": offset}

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
