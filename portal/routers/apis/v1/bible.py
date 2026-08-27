"""
Bible API Router
"""
from typing import Annotated
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query
from starlette import status

from portal.application.bible.bible_service import BibleService
from portal.application.bible.commands import ListVersionsQuery, SearchVersesCommand
from portal.application.bible.mappers import (
    bible_book_list_to_api,
    bible_chapter_to_api,
    bible_search_page_to_api,
    bible_version_list_to_api,
)
from portal.container import Container
from portal.serializers.apis.v1.bible import (
    BibleBookList,
    BibleChapterDetail,
    BibleSearchResponse,
    BibleVersionList,
)

router = APIRouter()


@router.get(
    path="/versions",
    response_model=BibleVersionList,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_bible_versions",
    summary="Get bible versions",
    description="Get list of available bible versions",
)
@inject
async def get_bible_versions(
    language: Annotated[str | None, Query(description="Language filter (e.g., 'zh-TW', 'zh-CN')")] = None,
    bible_service: BibleService = Depends(Provide[Container.bible_service]),
) -> BibleVersionList:
    result = await bible_service.list_versions(ListVersionsQuery(language=language))
    return bible_version_list_to_api(result)


@router.get(
    path="/versions/{bible_version_id}/books",
    response_model=BibleBookList,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_bible_books",
    summary="Get bible books",
    description="Get list of bible books for a specific version",
)
@inject
async def get_bible_books(
    bible_version_id: UUID,
    bible_service: BibleService = Depends(Provide[Container.bible_service]),
) -> BibleBookList:
    result = await bible_service.list_books(bible_version_id=bible_version_id)
    return bible_book_list_to_api(result)


@router.get(
    path="/books/{book_id}/chapters/{chapter}",
    response_model=BibleChapterDetail,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_bible_chapter",
    summary="Get bible chapter",
    description="Get bible chapter content",
)
@inject
async def get_bible_chapter(
    book_id: UUID,
    chapter: int,
    bible_service: BibleService = Depends(Provide[Container.bible_service]),
) -> BibleChapterDetail:
    result = await bible_service.get_chapter(book_id=book_id, chapter=chapter)
    return bible_chapter_to_api(result)


@router.get(
    path="/search",
    response_model=BibleSearchResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="search_bible_verses",
    summary="Search bible verses",
    description="Search bible verses by keyword",
)
@inject
async def search_bible_verses(
    q: Annotated[str, Query(description="Search keyword")],
    bible_version_id: Annotated[UUID | None, Query(description="Bible version ID filter (UUID)")] = None,
    book_id: Annotated[UUID | None, Query(description="Book ID filter (UUID)")] = None,
    limit: Annotated[int, Query(description="Result limit", ge=1, le=100)] = 20,
    offset: Annotated[int, Query(description="Result offset", ge=0)] = 0,
    bible_service: BibleService = Depends(Provide[Container.bible_service]),
) -> BibleSearchResponse:
    result = await bible_service.search_verses(
        SearchVersesCommand(
            q=q,
            bible_version_id=bible_version_id,
            book_id=book_id,
            limit=limit,
            offset=offset,
        )
    )
    return bible_search_page_to_api(result)
