"""
Member authentication serializers.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.common.mixins import UUIDModel
from portal.serializers.mixins import LoginResponse, TokenResponse


class MemberRegisterRequest(BaseModel):
    """End user password registration body."""

    email: str = Field(..., description="End user email")
    password: str = Field(..., description="End user password")
    display_name: str = Field(..., description="Display name for Preferences")


class MemberLoginRequest(BaseModel):
    """End user password login body."""

    email: str = Field(..., description="End user email")
    password: str = Field(..., description="End user password")


class MemberInfo(UUIDModel):
    """End user profile for app auth responses."""

    email: str = Field(..., description="Member email")
    first_name: str = Field(..., description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    preferred_name: Optional[str] = Field(None, description="Preferred display name", serialization_alias="preferredName")
    roles: list[str] = Field(default_factory=list, description="Roles")
    preferred_locale_id: Optional[UUID] = Field(None, description="Preferred locale id", serialization_alias="preferredLocaleId")
    last_login_at: Optional[datetime] = Field(None, description="Last login time")


class MemberLoginResponse(LoginResponse):
    """Member login / register response."""

    member: MemberInfo = Field(..., description="End user info (id is app.user.id)")
