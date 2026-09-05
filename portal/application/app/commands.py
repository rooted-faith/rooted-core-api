"""
Commands for End user / identity provisioning.
"""

from datetime import time
from typing import Optional

from pydantic import BaseModel, Field


class ProvisionIdentityCommand(BaseModel):
    """
    Provision a shared auth credential.

    When create_end_user is True (app signup), also create app.user + Preferences.
    When False (admin-only), skip End user identity entirely.
    """

    email: str = Field(...)
    password: Optional[str] = Field(default=None, description="Required for Admin/password paths; null for passwordless End users")
    display_name: Optional[str] = Field(default=None)
    create_end_user: bool = Field(default=True)
    is_admin: bool = Field(default=False)
    is_superuser: bool = Field(default=False)
    locale: str = Field(default="zh-Hant")
    theme: str = Field(default="system")
    font_scale: str = Field(default="M")
    bible_version: str = Field(default="cuv1919")
    stage: Optional[str] = Field(default=None)
    reminder_time: Optional[time] = Field(default=None)
    reminder_enabled: bool = Field(default=False)
