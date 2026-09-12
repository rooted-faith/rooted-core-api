"""Admin Bible response serializers."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class AdminBibleVersion(BaseModel):
    id: UUID = Field(...)
    youversion_bible_id: str = Field(..., serialization_alias="youversionBibleId")
    abbreviation: str = Field(...)
    title: str = Field(...)
    localized_title: str = Field(..., serialization_alias="localizedTitle")
    localized_abbreviation: str | None = Field(default=None, serialization_alias="localizedAbbreviation")
    language_tag: str = Field(..., serialization_alias="languageTag")
    is_active: bool = Field(..., serialization_alias="isActive")

    @field_serializer("id")
    def serialize_id(self, value: UUID, _info) -> str:
        return str(value)


class AdminBibleVersionList(BaseModel):
    versions: list[AdminBibleVersion] = Field(default_factory=list)


class AdminBibleBook(BaseModel):
    id: UUID = Field(...)
    book_code: str = Field(..., serialization_alias="bookCode")
    title: str = Field(...)
    full_title: str | None = Field(default=None, serialization_alias="fullTitle")
    abbreviation: str | None = Field(default=None)
    canon: str = Field(...)
    sequence: float = Field(...)
    chapter_count: int = Field(..., serialization_alias="chapterCount")

    @field_serializer("id")
    def serialize_id(self, value: UUID, _info) -> str:
        return str(value)


class AdminBibleBookList(BaseModel):
    old_testament: list[AdminBibleBook] = Field(default_factory=list, serialization_alias="oldTestament")
    new_testament: list[AdminBibleBook] = Field(default_factory=list, serialization_alias="newTestament")


class AdminBibleVerse(BaseModel):
    passage_id: str = Field(..., serialization_alias="passageId")
    verse: int = Field(...)
    verse_end: int | None = Field(default=None, serialization_alias="verseEnd")
    lines: list[dict[str, Any]] | None = Field(default=None)


class AdminBibleChapterDetail(BaseModel):
    bible_version_id: UUID = Field(..., serialization_alias="bibleVersionId")
    youversion_bible_id: str = Field(..., serialization_alias="youversionBibleId")
    bible_title: str = Field(..., serialization_alias="bibleTitle")
    book_id: UUID = Field(..., serialization_alias="bookId")
    book_code: str = Field(..., serialization_alias="bookCode")
    book_name: str = Field(..., serialization_alias="bookName")
    chapter: int = Field(...)
    verses: list[AdminBibleVerse] = Field(default_factory=list)

    @field_serializer("bible_version_id", "book_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)
