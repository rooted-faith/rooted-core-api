"""
End user and Preferences domain entities.

Product rows key off EndUser.id (app.user.id), not auth.user.id.
"""

from datetime import time
from typing import Optional
from uuid import UUID

from pydantic import Field

from portal.domain.common.mixins import UUIDBaseModel


class EndUser(UUIDBaseModel):
    """Product End user identity — separate UUID from the auth credential."""

    auth_user_id: UUID = Field(..., description="FK to auth.user credential row")


class UserPreferences(UUIDBaseModel):
    """1:1 Preferences for an End user (presentation / reminder settings)."""

    user_id: UUID = Field(..., description="FK to app.user.id (End user), not auth.user")
    display_name: str = Field(...)
    locale: str = Field(default="zh-Hant")
    theme: str = Field(default="system")
    font_scale: str = Field(default="M")
    # Soft string catalog key (e.g. cuv1919); not a hard FK to bible.versions.
    bible_version: str = Field(default="cuv1919")
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None)
    reminder_enabled: bool = Field(default=False)
