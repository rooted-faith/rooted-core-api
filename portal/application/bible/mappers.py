"""
Map bible application results to API serializers.
"""

from portal.application.bible.results import (
    BibleBookListResult,
    BibleChapterResult,
    BibleSearchPageResult,
    BibleVersionListResult,
)
from portal.serializers.apis.v1.bible import (
    BibleBook,
    BibleBookList,
    BibleChapterDetail,
    BibleSearchResponse,
    BibleSearchResult,
    BibleVerse,
    BibleVersion,
    BibleVersionList,
)


def bible_version_list_to_api(result: BibleVersionListResult) -> BibleVersionList:
    return BibleVersionList(versions=[BibleVersion.model_validate(item) for item in result.versions])


def bible_book_list_to_api(result: BibleBookListResult) -> BibleBookList:
    return BibleBookList(
        old_testament=[BibleBook.model_validate(item) for item in result.old_testament],
        new_testament=[BibleBook.model_validate(item) for item in result.new_testament],
    )


def bible_chapter_to_api(result: BibleChapterResult) -> BibleChapterDetail:
    return BibleChapterDetail(
        bible_version_id=result.bible_version_id,
        youversion_bible_id=result.youversion_bible_id,
        bible_title=result.bible_title,
        book_id=result.book_id,
        book_code=result.book_code,
        book_name=result.book_name,
        chapter=result.chapter,
        verses=[BibleVerse.model_validate(item) for item in result.verses],
    )


def bible_search_page_to_api(result: BibleSearchPageResult) -> BibleSearchResponse:
    return BibleSearchResponse(
        results=[BibleSearchResult.model_validate(item) for item in result.results],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )
