"""JSON/JSONB codec round trip against a real PostgreSQL connection."""

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("db_session", [False, True], ids=["connection", "pool"], indirect=True)
async def test_jsonb_binds_and_returns_python_values(db_session) -> None:
    lines = [{"type": "line", "fragments": [{"text": "In the beginning"}]}]

    assert await db_session.fetchval("SELECT $1::jsonb", lines) == lines
    assert await db_session.fetchval("SELECT $1::jsonb", "America/Toronto") == "America/Toronto"
    assert await db_session.fetchval("SELECT $1::jsonb", None) is None


@pytest.mark.asyncio
async def test_json_query_results_are_decoded(db_session) -> None:
    assert await db_session.fetchval("SELECT json_build_object('id', 1)") == {"id": 1}
