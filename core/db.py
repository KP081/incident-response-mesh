"""Shared async DB engine + table definitions for real telemetry storage.

Reuses the same DATABASE_URL as core/config.py -- so this works against
local sqlite (fast, no network) during dev and against Neon Postgres in
production, with zero code branching. This mirrors exactly how ADK's own
DatabaseSessionService is wired.

Caveat: seed_telemetry() (in tools/telemetry_tools.py) clears old rows for
a service before writing new ones. That's correct for this single-incident-
at-a-time demo, but NOT how a real multi-tenant system would work -- a real
system would scope every query by a trace/incident ID, not just service
name. Worth knowing the difference if this pattern comes up in an interview.
"""

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import DATABASE_URL, get_session_service_kwargs

_engine = create_async_engine(DATABASE_URL, **get_session_service_kwargs())
metadata = MetaData()

service_logs = Table(
    "service_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("service_name", String, nullable=False, index=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("level", String, nullable=False),
    Column("msg", String, nullable=False),
)

service_metrics = Table(
    "service_metrics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("service_name", String, nullable=False, index=True),
    Column("metric", String, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("value", Float, nullable=False),
)


async def init_telemetry_tables() -> None:
    """Idempotent -- safe to call before every run."""
    async with _engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


def get_engine():
    return _engine