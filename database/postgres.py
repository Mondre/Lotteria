"""Backend PostgreSQL/Neon: stesso dominio e transazioni del backend SQLite."""
from contextlib import contextmanager
import os
from pathlib import Path

from database.store import Store
from games.rules import RuleRegistry


def connection_options(dsn: str) -> dict:
    from psycopg.conninfo import conninfo_to_dict
    try:
        options = conninfo_to_dict(dsn)
    except Exception:
        raise ValueError("DATABASE_URL PostgreSQL non valida") from None
    host = options.get("host", "")
    if not host:
        raise ValueError("DATABASE_URL deve specificare un host PostgreSQL")
    # I soli test locali possono usare socket Unix/TCP senza TLS.
    local = host in ("localhost", "127.0.0.1", "::1") or host.startswith("/")
    if not local:
        import certifi
        # libpq del wheel binario può cercare le CA in percorsi non presenti su Render.
        # Un bundle esplicito evita di dipendere dai percorsi OpenSSL del sistema.
        root = options.get("sslrootcert") or os.environ.get("PGSSLROOTCERT") or certifi.where()
        if root != "system":
            root = str(Path(root).expanduser())
            if not Path(root).is_file():
                raise ValueError("Il bundle CA PostgreSQL configurato non è disponibile")
        options.update(sslmode="verify-full", sslrootcert=root)
    options["connect_timeout"] = "10"
    return options


class Connection:
    """Porta le query qmark del repository condiviso ai parametri psycopg."""
    def __init__(self, raw):
        self.raw = raw
        self.write_locked = False

    def execute(self, query, parameters=()):
        # Solo query interne statiche usano '?'; nessuna interpolazione di input.
        values = tuple(int(value) if isinstance(value, bool) else value for value in parameters)
        return self.raw.execute(query.replace("?", "%s"), values)


class PostgresStore(Store):
    backend = "postgresql"

    def __init__(self, dsn: str, rules: RuleRegistry):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        self.rules = rules
        options = connection_options(dsn)
        self.pool = ConnectionPool(conninfo="", kwargs={**options, "row_factory": dict_row, "prepare_threshold": None},
                                   min_size=0, max_size=3, timeout=15,
                                   check=ConnectionPool.check_connection, open=False)
        # Evitare che i messaggi del pool registrino un DSN con credenziali.
        self.pool.reconnect_timeout = 1
        self.pool.open()
        try:
            # Inizializzazione sincrona con errore sanitizzato, senza retry infiniti.
            with self.pool.connection() as raw:
                raw.execute("SELECT pg_advisory_xact_lock(826491017)")
                exists = raw.execute("SELECT to_regclass('schema_version') AS name").fetchone()["name"]
                if exists:
                    versions = raw.execute("SELECT version FROM schema_version").fetchall()
                    if any(row["version"] not in (2, 3, 4) for row in versions):
                        raise ValueError("Versione database PostgreSQL non supportata")
                raw.execute(Path(__file__).with_name("postgres_schema.sql").read_text(encoding="utf-8"))
        except Exception:
            self.pool.close()
            raise RuntimeError("Avvio PostgreSQL fallito: verificare DATABASE_URL, TLS e autorizzazioni del progetto Neon") from None

    @contextmanager
    def connect(self):
        active = self.active_connection()
        if active is not None:
            yield active
            return
        with self.pool.connection() as raw:
            yield Connection(raw)

    def begin_write(self, connection) -> None:
        # Serializza le scritture dell'applicazione, comprese verifica duplicati e inserimento.
        if not connection.write_locked:
            connection.execute("SELECT pg_advisory_xact_lock(826491018)")
            connection.write_locked = True

    def close(self) -> None:
        self.pool.close()
