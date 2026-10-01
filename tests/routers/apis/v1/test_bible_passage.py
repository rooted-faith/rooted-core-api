from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from portal.application.bible.commands import ReadPassageQuery
from portal.application.bible.results import BiblePassageResult
from portal.domain.bible.constants import BibleErrorCode
from portal.domain.bible.entities import BibleVerse
from portal.exceptions.responses import NotFoundException
from portal.routers.apis.v1.bible import get_bible_passage, router

VERSE = BibleVerse(passage_id="GEN.1.1", verse=1, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "In the beginning"}]}])


class StubBibleService:
    def __init__(self, result: BiblePassageResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.captured: ReadPassageQuery | None = None

    async def read_passage(self, query: ReadPassageQuery) -> BiblePassageResult:
        self.captured = query
        if self._error is not None:
            raise self._error
        return self._result


def test_passage_route_is_available_as_get():
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert any(route.path == "/versions/{bible_version_id}/passages" and "GET" in route.methods for route in routes)


@pytest.mark.asyncio
async def test_get_bible_passage_passes_query_params_and_returns_camel_case_payload():
    version_id = uuid4()
    result = BiblePassageResult(start="GEN.1.1", end="GEN.1.1", ref="Genesis 1:1", verses=[VERSE])
    service = StubBibleService(result=result)

    response = await get_bible_passage(bible_version_id=version_id, start="GEN.1.1", end="GEN.1.1", bible_service=service)
    payload = response.model_dump(mode="json", by_alias=True)

    assert service.captured == ReadPassageQuery(bible_version_id=version_id, passage_start="GEN.1.1", passage_end="GEN.1.1")
    assert payload == {
        "start": "GEN.1.1",
        "end": "GEN.1.1",
        "ref": "Genesis 1:1",
        "verses": [
            {
                "passageId": "GEN.1.1",
                "verse": 1,
                "verseEnd": None,
                "lines": [{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "In the beginning"}]}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_get_bible_passage_propagates_not_found_for_unresolved_passage():
    service = StubBibleService(error=NotFoundException(detail="Passage reference could not be resolved", error_code=BibleErrorCode.PASSAGE_NOT_FOUND))

    with pytest.raises(NotFoundException) as exc_info:
        await get_bible_passage(bible_version_id=uuid4(), start="GEN.1.1", end="GEN.1.1", bible_service=service)

    assert exc_info.value.error_code == BibleErrorCode.PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_get_bible_passage_propagates_not_found_for_unavailable_version():
    service = StubBibleService(error=NotFoundException(detail="Bible version not found or inactive", error_code=BibleErrorCode.VERSION_NOT_FOUND))

    with pytest.raises(NotFoundException) as exc_info:
        await get_bible_passage(bible_version_id=uuid4(), start="GEN.1.1", end="GEN.1.1", bible_service=service)

    assert exc_info.value.error_code == BibleErrorCode.VERSION_NOT_FOUND
