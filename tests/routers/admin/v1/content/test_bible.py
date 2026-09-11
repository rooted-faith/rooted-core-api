from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.routers.admin.v1.content.bible import get_bible_chapter, router


class StubBibleService:
    async def get_chapter(self, book_id, chapter):
        return BibleChapter(
            bible_version_id=uuid4(),
            youversion_bible_id="3034",
            bible_title="World English Bible",
            book_id=book_id,
            book_code="JHN",
            book_name="John",
            chapter=chapter,
            verses=[BibleVerse(passage_id="JHN.3.16", verse=16, lines=None)],
        )


def test_admin_bible_routes_require_admin_devotion_read_permission():
    routes = [route for route in router.routes if isinstance(route, APIRoute)]

    assert {(route.path, frozenset(route.methods)) for route in routes} == {
        ("/versions", frozenset({"GET"})),
        ("/versions/{bible_version_id}/books", frozenset({"GET"})),
        ("/books/{book_id}/chapters/{chapter}", frozenset({"GET"})),
    }
    for route in routes:
        auth_config = route.endpoint.__auth_config__
        assert auth_config.require_auth is True
        assert auth_config.is_admin is True
        assert auth_config.permission_codes == ["content:devotion:read"]


@pytest.mark.asyncio
async def test_admin_chapter_verses_include_passage_id():
    response = await get_bible_chapter(book_id=uuid4(), chapter=3, bible_service=StubBibleService())

    assert response.model_dump(mode="json", by_alias=True)["verses"] == [{"passageId": "JHN.3.16", "verse": 16, "verseEnd": None, "lines": None}]
