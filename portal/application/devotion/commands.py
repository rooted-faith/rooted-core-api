"""Devotion authoring application commands."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from portal.domain.devotion.constants import DevotionStatus


class CreateDevotionCommand(BaseModel):
    passage_start: str = Field(min_length=1, max_length=50)
    passage_end: str = Field(min_length=1, max_length=50)


class UpdateDevotionCommand(CreateDevotionCommand):
    pass


class UpsertDevotionTranslationCommand(BaseModel):
    reflect: list[str] = Field(default_factory=list)
    apply: str = Field(min_length=1)
    pray: str = Field(min_length=1)


class UpsertLessonNoteCommand(BaseModel):
    date: date
    body: str | None = None
    reflects: list[str | None] = Field(default_factory=list)


class DevotionPagesQuery(BaseModel):
    page: int = Field(default=0, ge=0)
    page_size: int = Field(default=10, ge=1, le=100)
    status: Optional[DevotionStatus] = None
    missing_locale: Optional[str] = Field(default=None, min_length=1, max_length=64)
