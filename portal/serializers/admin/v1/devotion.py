"""Admin Devotion authoring and scheduling serializers."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.devotion.constants import DevotionStatus
from portal.serializers.mixins import PaginationBaseResponseModel
from portal.serializers.mixins.model_mixins import UUIDBaseModel


class AdminDevotionCreate(BaseModel):
    passage_start: str = Field(min_length=1, max_length=50, serialization_alias="passageStart")
    passage_end: str = Field(min_length=1, max_length=50, serialization_alias="passageEnd")


class AdminDevotionUpdate(AdminDevotionCreate):
    pass


class AdminDevotionTranslationUpsert(BaseModel):
    reflect: list[str] = Field(default_factory=list)
    apply: str = Field(min_length=1)
    pray: str = Field(min_length=1)


class AdminDevotionQuery(BaseModel):
    page: int = Field(default=0, ge=0)
    page_size: int = Field(default=10, ge=1, le=100, serialization_alias="pageSize")
    status: DevotionStatus | None = None
    missing_locale: str | None = Field(default=None, serialization_alias="missingLocale")


class AdminDevotionTranslation(BaseModel):
    locale_id: UUID = Field(serialization_alias="localeId")
    locale_code: str = Field(serialization_alias="localeCode")
    reflect: list[str] = Field(default_factory=list)
    apply: str
    pray: str


class AdminDevotionItem(UUIDBaseModel):
    passage_start: str = Field(serialization_alias="passageStart")
    passage_end: str = Field(serialization_alias="passageEnd")
    status: DevotionStatus


class AdminDevotionDetail(AdminDevotionItem):
    translations: list[AdminDevotionTranslation] = Field(default_factory=list)


class AdminDevotionPages(PaginationBaseResponseModel):
    total_pages: int = Field(serialization_alias="totalPages")
    items: list[AdminDevotionItem] = Field(default_factory=list)


class AdminDailyLessonScheduleUpsert(BaseModel):
    devotion_id: UUID = Field(serialization_alias="devotionId")


class AdminDailyLessonScheduleQuery(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")


class AdminDailyLessonScheduleItem(BaseModel):
    date: date
    devotion_id: UUID | None = Field(default=None, serialization_alias="devotionId")


class AdminDailyLessonScheduleRange(BaseModel):
    items: list[AdminDailyLessonScheduleItem] = Field(default_factory=list)
    scheduled_through: date | None = Field(default=None, serialization_alias="scheduledThrough")
