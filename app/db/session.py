from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base

_engine = create_async_engine(get_settings().database_url)
async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

# There's no migration framework here (no Alembic) - create_all only creates missing
# tables, it never adds columns to a table that already exists. For a table that
# predates a given column, add it by hand here so an existing bot.db on a server keeps
# working after a deploy that added fields, instead of crashing on the first query.
_STRATEGY_INSTANCE_COLUMN_MIGRATIONS = {
    "profit_alert_pct": "REAL NOT NULL DEFAULT 10.0",
    "loss_alert_pct": "REAL NOT NULL DEFAULT 15.0",
    "alert_capital_base": "REAL",
    "profit_alerts_sent": "INTEGER NOT NULL DEFAULT 0",
    "loss_alerts_sent": "INTEGER NOT NULL DEFAULT 0",
}


def _add_missing_strategy_instance_columns(conn) -> None:
    existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(strategy_instances)").fetchall()}
    for column, ddl in _STRATEGY_INSTANCE_COLUMN_MIGRATIONS.items():
        if column not in existing:
            conn.exec_driver_sql(f"ALTER TABLE strategy_instances ADD COLUMN {column} {ddl}")


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_strategy_instance_columns)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
