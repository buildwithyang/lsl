from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session as OrmSession, sessionmaker

from lsl.core.config import Settings

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


@dataclass(slots=True)
class DatabaseResources:
    pool: ConnectionPool | None = None
    engine: Engine | None = None
    session_factory: sessionmaker[OrmSession] | None = None


def to_sqlalchemy_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+"):
        return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def create_database_resources(settings: Settings) -> DatabaseResources:
    if not settings.DATABASE_URL:
        return DatabaseResources()

    database_url = settings.DATABASE_URL
    sqlalchemy_database_url = to_sqlalchemy_database_url(database_url)

    connect_pool = None
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }

    if sqlalchemy_database_url.startswith("sqlite:///"):
        sqlite_path = sqlalchemy_database_url[len("sqlite:///") :]
        if sqlite_path and sqlite_path != ":memory:" and not sqlite_path.startswith("file:"):
            Path(sqlite_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "psycopg_pool is required. Run: uv pip install psycopg-pool"
            ) from exc

        connect_pool = ConnectionPool(
            conninfo=database_url,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            timeout=settings.DB_POOL_TIMEOUT,
            open=False,
        )
        connect_pool.open(wait=True)

    engine = create_engine(
        sqlalchemy_database_url,
        **engine_kwargs,
    )
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return DatabaseResources(
        pool=connect_pool,
        engine=engine,
        session_factory=session_factory,
    )


def _add_missing_columns(engine: Engine) -> None:
    """ALTER TABLE ADD COLUMN for any new nullable columns added to models.

    `Base.metadata.create_all()` only creates tables that don't exist; it never
    alters existing tables. When a column is added to a SQLAlchemy model, this
    helper adds the corresponding column on next startup so existing databases
    stay in sync without manual migrations.

    Safety: only adds NULLABLE columns. NOT NULL columns require manual
    migration (a default would be ambiguous), so they're skipped with a warning.
    Never drops or modifies existing columns.
    """
    inspector = inspect(engine)
    dialect = engine.dialect
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue
            actual_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in actual_cols:
                    continue
                if not column.nullable:
                    logger.warning(
                        "Skipping ALTER TABLE %s ADD COLUMN %s: column is NOT NULL "
                        "and requires a manual migration.",
                        table_name,
                        column.name,
                    )
                    continue
                column_type = column.type.compile(dialect=dialect)
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column.name} {column_type}'))
                logger.info(
                    "Added missing column %s.%s (%s) via auto-migration",
                    table_name,
                    column.name,
                    column_type,
                )


def close_database_resources(resources: DatabaseResources) -> None:
    if resources.pool is not None:
        resources.pool.close()
    if resources.engine is not None:
        resources.engine.dispose()
