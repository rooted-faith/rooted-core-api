"""ORM seam: bible catalog tables live under the bible schema with plural names."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from portal.models import BibleBook, BibleVerse, BibleVersion


def test_bible_version_maps_to_versions_table() -> None:
    assert BibleVersion.__table__.schema == "bible"
    assert BibleVersion.__tablename__ == "versions"


def test_bible_book_maps_to_books_table() -> None:
    assert BibleBook.__table__.schema == "bible"
    assert BibleBook.__tablename__ == "books"


def test_bible_verse_maps_to_verses_table() -> None:
    assert BibleVerse.__table__.schema == "bible"
    assert BibleVerse.__tablename__ == "verses"


def test_bible_verse_keeps_address_columns_uniques_and_audit_timestamps() -> None:
    columns = BibleVerse.__table__.c
    assert {"id", "book_id", "chapter", "verse", "passage_id", "created_at", "updated_at"} <= set(columns.keys())
    unique_columns = [
        {column.name for column in constraint.columns} for constraint in BibleVerse.__table__.constraints if isinstance(constraint, sa.UniqueConstraint)
    ]
    assert {"book_id", "passage_id"} in unique_columns
    assert {"book_id", "chapter", "verse"} in unique_columns


def test_bible_verse_replaces_content_with_nullable_lines_search_text_and_verse_end() -> None:
    columns = BibleVerse.__table__.c
    assert "content" not in columns
    assert columns.verse_end.nullable is True
    assert isinstance(columns.verse_end.type, sa.Integer)
    assert columns.lines.nullable is True
    assert isinstance(columns.lines.type, JSONB)
    assert columns.search_text.nullable is True
    assert isinstance(columns.search_text.type, sa.Text)


def test_bible_version_and_book_columns_are_unchanged() -> None:
    assert set(BibleVersion.__table__.c.keys()) == {
        "id",
        "youversion_bible_id",
        "abbreviation",
        "title",
        "localized_title",
        "localized_abbreviation",
        "language_tag",
        "copyright",
        "promotional_content",
        "publisher_url",
        "youversion_deep_link",
        "organization_id",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert set(BibleBook.__table__.c.keys()) == {
        "id",
        "bible_version_id",
        "book_code",
        "title",
        "full_title",
        "abbreviation",
        "canon",
        "chapter_count",
        "sequence",
        "created_at",
        "updated_at",
    }
