"""ORM seam: bible catalog tables live under the bible schema with plural names."""

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
