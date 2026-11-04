import os

from config.settings import data_directory
from database.store import Store
from games.rules import RuleRegistry


def create_store() -> Store:
    rules = RuleRegistry()
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL deve essere un URL PostgreSQL")
        from database.postgres import PostgresStore
        return PostgresStore(dsn, rules)
    if os.environ.get("RENDER") == "true":
        raise ValueError("DATABASE_URL è obbligatoria su Render: SQLite locale non è persistente")
    return Store(data_directory() / "lottopredict.sqlite3", rules)
