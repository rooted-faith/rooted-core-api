"""Tests for Bible API response mappings."""

from uuid import uuid4

from portal.application.bible.mappers import bible_chapter_to_admin_api, bible_chapter_to_api
from portal.domain.bible.entities import BibleChapter, BibleVerse


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
