"""
Member End user serializers (camelCase JSON via serialization_alias).
"""

from datetime import time
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from portal.domain.app.constants import WeekStart


class MemberPreferences(BaseModel):
    """Synced End-user Preferences."""

    display_name: str = Field(..., serialization_alias="displayName")
    theme: str = Field(...)
    font_scale: str = Field(..., serialization_alias="fontScale")
    bible_version: str = Field(..., serialization_alias="bibleVersion")
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None, serialization_alias="reminderTime")
    reminder_enabled: bool = Field(..., serialization_alias="reminderEnabled")
    week_start: WeekStart = Field(..., serialization_alias="weekStart")


class UpdateMemberPreferences(BaseModel):
    """Partial Preferences update; omitted fields remain unchanged."""

    display_name: Optional[str] = Field(default=None)
    theme: Optional[str] = Field(default=None)
    font_scale: Optional[str] = Field(default=None)
    bible_version: Optional[str] = Field(default=None)
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None)
    reminder_enabled: Optional[bool] = Field(default=None)
    week_start: Optional[WeekStart] = Field(default=None)

    @field_validator("week_start")
    @classmethod
    def week_start_must_not_be_null(cls, value: Optional[WeekStart]) -> WeekStart:
        if value is None:
            raise ValueError("week_start must be sunday or monday")
        return value
