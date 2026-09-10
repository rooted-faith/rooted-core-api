"""
Results for End user / identity provisioning.
"""

from datetime import time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.app.constants import WeekStart


class ProvisionIdentityResult(BaseModel):
    """Outcome of credential (+ optional End user) provisioning."""

    auth_user_id: UUID = Field(...)
    end_user_id: Optional[UUID] = Field(default=None, description="app.user.id when create_end_user was True; None for admin-only")


class PreferencesResult(BaseModel):
    """Current synced Preferences for one End user."""

    display_name: str = Field(...)
    theme: str = Field(...)
    font_scale: str = Field(...)
    bible_version: str = Field(...)
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None)
    reminder_enabled: bool = Field(...)
    week_start: WeekStart = Field(...)
