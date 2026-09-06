"""
Auth domain entities.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.common.mixins import UUIDModel
from portal.libs.consts.enums import Gender


class User(UUIDModel):
    """Core user account with profile fields."""

    email: Optional[str] = Field(default=None, description="User email address")
    verified: bool = Field(default=False, description="Whether the user is verified")
    is_active: bool = Field(default=True, description="Whether the user is active")
    is_superuser: bool = Field(default=False, description="Whether the user is a superuser")
    is_admin: bool = Field(default=False, description="Whether the user can access admin portal")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login timestamp")
    first_name: Optional[str] = Field(default=None, description="First name")
    last_name: Optional[str] = Field(default=None, description="Last name")
    preferred_name: Optional[str] = Field(default=None, description="Preferred display name")
    preferred_locale_id: Optional[UUID] = Field(default=None, description="Preferred locale id")
    gender: Optional[Gender] = Field(default=None, description="Gender")


class GoogleIdentityClaims(BaseModel):
    """Verified Google ID token claims relevant to Admin sign-in resolution (ADR 0006)."""

    subject: str = Field(..., description="Google account stable subject (sub); stable across Rooted's OAuth clients")
    email: Optional[str] = Field(default=None, description="Email claim as asserted by Google")
    email_verified: bool = Field(default=False, description="Whether Google verified the email claim")
    audience: str = Field(..., description="Token audience (aud) — the Client ID the token was issued for")
