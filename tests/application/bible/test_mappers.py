"""Tests for Bible API response mappings."""

from uuid import uuid4

from portal.application.bible.mappers import bible_chapter_to_admin_api, bible_chapter_to_api, bible_version_list_to_api
from portal.application.bible.results import BibleVersionListResult
from portal.domain.bible.entities import BibleChapter, BibleVerse, BibleVersion


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
