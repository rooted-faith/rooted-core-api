"""
Commands for End user / identity provisioning.
"""

from datetime import time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.app.constants import WeekStart


class ProvisionIdentityCommand(BaseModel):
    """
    Provision a shared auth credential.

    When create_end_user is True, also create app.user + Preferences.
    When False (admin-only), skip End user identity entirely.
    """

    email: str = Field(...)
    password: Optional[str] = Field(default=None, description="Required for Admin credential provisioning; null for End-user sign-in provisioning")
    display_name: Optional[str] = Field(default=None)
    create_end_user: bool = Field(default=True)
    is_admin: bool = Field(default=False)
    is_superuser: bool = Field(default=False)
    theme: str = Field(default="system")
    font_scale: str = Field(default="M")
    bible_version: str = Field(default="cuv1919")
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None)
    reminder_enabled: bool = Field(default=False)


class UpdatePreferencesCommand(BaseModel):
    """Fields a signed-in End user may update on their Preferences."""

    display_name: Optional[str] = Field(default=None)
    theme: Optional[str] = Field(default=None)
    font_scale: Optional[str] = Field(default=None)
    bible_version: Optional[str] = Field(default=None)
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None)
    reminder_enabled: Optional[bool] = Field(default=None)
    week_start: Optional[WeekStart] = Field(default=None)
