"""
Bible catalog ORM: versions, books, and verses (verse-per-row).

Tables live in the bible schema as versions / books / verses (ADR 0004).
Passage remains an addressing/read concept over verses — no bible_passages table.
"""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from portal.libs.database.orm import ModelBase
from portal.models.mixins import AuditCreatedAtMixin, AuditUpdatedAtMixin, SortableMixin


class BibleVersion(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin):
    """Bible Version Model."""

    __tablename__ = "versions"
    __extra_table_args__ = ({"comment": "Bible versions table"},)

    youversion_bible_id = Column(sa.String(20), nullable=False, unique=True, comment="YouVersion bible_id, e.g., '1392'", index=True)
    abbreviation = Column(sa.String(50), nullable=False, comment="English abbreviation, e.g., 'CCBT'")
    title = Column(sa.String(255), nullable=False, comment="English title")
    localized_title = Column(sa.String(255), nullable=False, comment="Localized title")
    localized_abbreviation = Column(sa.String(50), nullable=True, comment="Localized abbreviation")
    language_tag = Column(sa.String(20), nullable=False, comment="Language tag, e.g., 'zh-Hant-TW'", index=True)
    copyright = Column(sa.Text, nullable=True, comment="Copyright information")
    promotional_content = Column(sa.Text, nullable=True, comment="Promotional content")
    publisher_url = Column(sa.String(500), nullable=True, comment="Publisher URL")
    youversion_deep_link = Column(sa.String(500), nullable=True, comment="YouVersion deep link")
    organization_id = Column(UUID, nullable=True, comment="Organization ID")
    is_active = Column(sa.Boolean, default=True, nullable=False, comment="Is version active", index=True)


class BibleBook(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin, SortableMixin):
    """
    Bible Book Model.

    Book belongs to a Bible version. Each version has its own set of books.
    This design simplifies BibleVerse structure (only needs book_id).
    """

    __tablename__ = "books"
    __extra_table_args__ = (sa.UniqueConstraint("bible_version_id", "book_code"), {"comment": "Bible books table - books belong to a specific version"})

    bible_version_id = Column(UUID, sa.ForeignKey(BibleVersion.id, ondelete="CASCADE"), nullable=False, comment="Bible version ID", index=True)
    book_code = Column(sa.String(10), nullable=False, comment="Book code, e.g., 'GEN', 'MAT'", index=True)
    title = Column(sa.String(100), nullable=False, comment="Book title")
    full_title = Column(sa.String(100), nullable=True, comment="Full book title")
    abbreviation = Column(sa.String(10), nullable=True, comment="Book abbreviation")
    canon = Column(sa.String(20), nullable=False, comment="Canon type: 'old_testament' or 'new_testament'", index=True)
    chapter_count = Column(sa.Integer, nullable=False, comment="Number of chapters in this book")


class BibleVerse(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin):
    """
    Bible Verse Model (verse-per-row).

    Verse belongs to a book; book belongs to a version, so book_id identifies both.
    """

    __tablename__ = "verses"
    __extra_table_args__ = (
        sa.UniqueConstraint("book_id", "passage_id"),
        sa.UniqueConstraint("book_id", "chapter", "verse"),
        {"comment": "Bible verses table - verse belongs to a book (which belongs to a version)"},
    )

    book_id = Column(UUID, sa.ForeignKey(BibleBook.id, ondelete="CASCADE"), nullable=False, comment="Book ID (which also identifies the version)", index=True)
    chapter = Column(sa.Integer, nullable=False, comment="Chapter number", index=True)
    verse = Column(sa.Integer, nullable=False, comment="Verse number", index=True)
    passage_id = Column(sa.String(50), nullable=False, comment="Passage ID, e.g., 'GEN.1.1'", index=True)
    content = Column(sa.Text, nullable=False, comment="Verse content (version-specific)")
