"""Tests for BibleRepository."""

import pytest

from portal.infrastructure.persistence.repositories.bible.bible_repository import BibleRepository


class FailingSession:
    def __getattr__(self, name: str):
        raise AssertionError(f"search must not access the database through {name}")


@pytest.mark.asyncio
async def test_search_verses_returns_an_empty_page_without_read_time_fill() -> None:
    repository = BibleRepository(session=FailingSession())

    page = await repository.search_verses(q="beginning", bible_version_id=None, book_id=None, limit=20, offset=0)

    assert page.results == []
    assert page.total == 0
    assert page.limit == 20
    assert page.offset == 0
