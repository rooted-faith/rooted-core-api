"""
Member authentication serializers.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from portal.domain.auth.constants import OtpDeliveryMode
from portal.domain.common.mixins import UUIDModel
from portal.serializers.mixins import LoginResponse, TokenResponse


class MemberOtpRequest(BaseModel):
    """Request a one-time passcode by email."""

    email: EmailStr = Field(..., description="End user email")


class MemberOtpVerifyRequest(BaseModel):
    """Verify a one-time passcode and sign in."""

    email: EmailStr = Field(..., description="End user email")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="Six-digit one-time passcode", repr=False)


class MemberGoogleLoginRequest(BaseModel):
    """End-user Google ID-token sign-in request body (ADR 0008)."""

    id_token: str = Field(..., description="Google ID token from the app's Google sign-in client")


class MemberAppleLoginRequest(BaseModel):
    """End-user Sign in with Apple request body (ADR 0008)."""

    id_token: str = Field(..., description="Identity token from Sign in with Apple")


class MemberOtpRequestResponse(BaseModel):
    """Anti-enumeration acknowledgement."""

    message: str = Field(..., description="Acknowledgement for the selected delivery mode")
    delivery_mode: OtpDeliveryMode = Field(
        ...,
        description="How to obtain the passcode: `email` (sent to the address) or `fixed` (test passcode from the test team, no email sent)",
        serialization_alias="deliveryMode",
    )


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
    """Member login / verify response."""

    member: MemberInfo = Field(..., description="End user info (id is app.user.id)")
