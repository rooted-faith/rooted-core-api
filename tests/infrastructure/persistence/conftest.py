"""Real PostgreSQL session fixture for persistence tests."""

import pytest
import pytest_asyncio

from tests.infrastructure.persistence.db import open_session_or_skip


@pytest_asyncio.fixture(params=[False], ids=["connection"])
async def db_session(request: pytest.FixtureRequest):
    """Session whose writes are rolled back after the test; parametrize indirectly with use_pool."""
    session = await open_session_or_skip(request.param)
    # Fetch helpers do not open a transaction; execute() does, so every later write is rolled back.
    await session.execute("SELECT 1")
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
