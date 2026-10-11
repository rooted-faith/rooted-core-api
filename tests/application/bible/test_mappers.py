"""Tests for Bible API response mappings."""

from uuid import uuid4

from portal.application.bible.mappers import (
    bible_book_list_to_api,
    bible_chapter_to_admin_api,
    bible_chapter_to_api,
    bible_search_page_to_api,
    bible_version_list_to_api,
)
from portal.application.bible.results import BibleBookListResult, BibleVersionListResult
from portal.domain.bible.entities import BibleBook, BibleChapter, BibleSearchHit, BibleSearchPage, BibleVerse, BibleVersion


def test_chapter_mappers_expose_index_verse_shells_without_content() -> None:
    chapter = BibleChapter(
        bible_version_id=uuid4(),
        youversion_bible_id="1392",
        bible_title="當代譯本",
        book_id=uuid4(),
        book_code="GEN",
        book_name="Genesis",
        chapter=1,
        verses=[BibleVerse(passage_id="GEN.1.1", verse=1, lines=None)],
    )

    member_verse = bible_chapter_to_api(chapter).model_dump(by_alias=True)["verses"]
    admin_verse = bible_chapter_to_admin_api(chapter).model_dump(by_alias=True)["verses"]

    assert member_verse == [{"passageId": "GEN.1.1", "verse": 1, "verseEnd": None, "lines": None}]
    assert admin_verse == member_verse


def test_member_catalog_exposes_the_public_youversion_bridge_and_license_metadata() -> None:
    version = BibleVersion(
        id=uuid4(),
        youversion_bible_id="1392",
        abbreviation="CCBT",
        title="Chinese Contemporary Bible Traditional",
        localized_title="當代譯本",
        language_tag="zh-Hant-TW",
        copyright="Copyright Bible League International",
        publisher_url="https://www.bible.com/versions/1392",
        is_active=True,
    )

    payload = bible_version_list_to_api(BibleVersionListResult(versions=[version])).model_dump(by_alias=True)["versions"][0]

    assert payload["id"] == str(version.id)
    assert payload["youversionBibleId"] == "1392"
    assert payload["copyright"] == "Copyright Bible League International"
    assert payload["publisherUrl"] == "https://www.bible.com/versions/1392"


def _book(book_code: str, canon: str, sequence: float) -> BibleBook:
    return BibleBook(id=uuid4(), book_code=book_code, title=book_code.title(), canon=canon, sequence=sequence, chapter_count=1)


def test_member_book_list_maps_domain_books_for_both_testaments() -> None:
    genesis = _book("GEN", "old_testament", 1)
    matthew = _book("MAT", "new_testament", 40)

    payload = bible_book_list_to_api(BibleBookListResult(old_testament=[genesis], new_testament=[matthew])).model_dump(by_alias=True)

    assert payload["oldTestament"] == [
        {
            "id": str(genesis.id),
            "bookCode": "GEN",
            "title": "Gen",
            "fullTitle": None,
            "abbreviation": None,
            "canon": "old_testament",
            "sequence": 1.0,
            "chapterCount": 1,
        }
    ]
    assert [book["bookCode"] for book in payload["newTestament"]] == ["MAT"]
    assert payload["newTestament"][0]["id"] == str(matthew.id)


def test_member_search_page_maps_domain_hits() -> None:
    hit = BibleSearchHit(
        bible_version_id=uuid4(),
        youversion_bible_id="1392",
        bible_title="當代譯本",
        book_id=uuid4(),
        book_code="JHN",
        book_name="John",
        chapter=3,
        verse=16,
        content="For God so loved the world",
        highlight="<b>loved</b>",
    )

    payload = bible_search_page_to_api(BibleSearchPage(results=[hit], total=1, limit=20, offset=0)).model_dump(by_alias=True)

    assert payload == {
        "results": [
            {
                "bibleVersionId": str(hit.bible_version_id),
                "youversionBibleId": "1392",
                "bibleTitle": "當代譯本",
                "bookId": str(hit.book_id),
                "bookCode": "JHN",
                "bookName": "John",
                "chapter": 3,
                "verse": 16,
                "content": "For God so loved the world",
                "highlight": "<b>loved</b>",
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }
