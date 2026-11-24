"""
Auth application commands.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class LoginCommand(BaseModel):
    """Password login command."""

    email: str = Field(..., description="Admin email")
    password: str = Field(..., description="Admin password")


class AppOtpRequestCommand(BaseModel):
    """Request a one-time passcode by email (ADR 0008)."""

    email: str = Field(..., description="End user email")


class AppOtpVerifyCommand(BaseModel):
    """Verify a one-time passcode and sign in (or provision) the End user."""

    email: str = Field(..., description="End user email")
    code: str = Field(..., description="One-time passcode", repr=False)


class LoginWithoutValidateCommand(BaseModel):
    """Dev-only login command that skips password validation."""

    email: str = Field(..., description="Admin email")


class RefreshTokenCommand(BaseModel):
    """Refresh access token command."""

    refresh_token: str = Field(..., description="Opaque refresh token")


class MicrosoftLoginCommand(BaseModel):
    """Microsoft Entra ID login command."""

    id_token: str = Field(..., description="Microsoft ID token")


class AdminGoogleLoginCommand(BaseModel):
    """Admin Google ID-token sign-in command (ADR 0006)."""

    id_token: str = Field(..., description="Google ID token from Google Identity Services")


class AppGoogleLoginCommand(BaseModel):
    """End-user Google ID-token sign-in command (ADR 0008)."""

    id_token: str = Field(..., description="Google ID token from the app's Google sign-in client")


class AppAppleLoginCommand(BaseModel):
    """End-user Apple identity-token sign-in command (ADR 0008)."""

    id_token: str = Field(..., description="Identity token from Sign in with Apple")


class LogoutCommand(BaseModel):
    """Logout command."""

    access_token: str = Field(..., description="Access token to blacklist")
    refresh_token: str | None = Field(None, description="Refresh token to revoke")
