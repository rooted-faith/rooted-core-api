"""
Member Bible API serializers (camelCase JSON via serialization_alias).
"""

from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class BibleVersion(BaseModel):
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


class BibleVersionList(BaseModel):
    versions: list[BibleVersion] = Field(default_factory=list)


class BibleBook(BaseModel):
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


class BibleBookList(BaseModel):
    old_testament: list[BibleBook] = Field(default_factory=list, serialization_alias="oldTestament")
    new_testament: list[BibleBook] = Field(default_factory=list, serialization_alias="newTestament")


class BibleVerse(BaseModel):
    verse: int = Field(...)
    content: str = Field(...)


class BibleChapterDetail(BaseModel):
    bible_version_id: UUID = Field(..., serialization_alias="bibleVersionId")
    youversion_bible_id: str = Field(..., serialization_alias="youversionBibleId")
    bible_title: str = Field(..., serialization_alias="bibleTitle")
    book_id: UUID = Field(..., serialization_alias="bookId")
    book_code: str = Field(..., serialization_alias="bookCode")
    book_name: str = Field(..., serialization_alias="bookName")
    chapter: int = Field(...)
    verses: list[BibleVerse] = Field(default_factory=list)

    @field_serializer("bible_version_id", "book_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)


class BibleSearchResult(BaseModel):
    bible_version_id: UUID = Field(..., serialization_alias="bibleVersionId")
    youversion_bible_id: str = Field(..., serialization_alias="youversionBibleId")
    bible_title: str = Field(..., serialization_alias="bibleTitle")
    book_id: UUID = Field(..., serialization_alias="bookId")
    book_code: str = Field(..., serialization_alias="bookCode")
    book_name: str = Field(..., serialization_alias="bookName")
    chapter: int = Field(...)
    verse: int = Field(...)
    content: str = Field(...)
    highlight: str | None = Field(default=None)

    @field_serializer("bible_version_id", "book_id")
    def serialize_uuid(self, value: UUID, _info) -> str:
        return str(value)


class BibleSearchResponse(BaseModel):
    results: list[BibleSearchResult] = Field(default_factory=list)
    total: int = Field(...)
    limit: int = Field(...)
    offset: int = Field(...)
