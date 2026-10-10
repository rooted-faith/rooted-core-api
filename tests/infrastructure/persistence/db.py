"""Real PostgreSQL sessions for persistence tests; skipped when no database is reachable."""

import asyncio

import pytest

from portal.libs.database import Session
from portal.libs.database.aio_pg import PostgresConnection


async def open_session_or_skip(use_pool: bool = False) -> Session:
    session = Session(echo=False, use_poll=use_pool, postgres_connection=PostgresConnection())
    try:
        await asyncio.wait_for(session.fetchval("SELECT 1"), timeout=3)
    except Exception as error:  # noqa: BLE001 - no reachable database means nothing to test
        await session.close()
        pytest.skip(f"PostgreSQL not reachable: {error}")
    return session
