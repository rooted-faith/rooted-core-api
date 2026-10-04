"""
Auth domain ports.
"""

from typing import Any, Optional, Protocol
from uuid import UUID

from portal.application.auth.results import UserDetail, UserSensitive
from portal.domain.auth.entities import AppleIdentityClaims, GoogleIdentityClaims


class UserRepositoryPort(Protocol):
    """Load and mutate user accounts."""

    async def get_sensitive_by_email(self, email: str) -> Optional[UserSensitive]: ...

    async def get_sensitive_by_email_without_profile(self, email: str) -> Optional[UserSensitive]: ...

    async def get_sensitive_by_id(self, user_id: UUID) -> Optional[UserSensitive]: ...

    async def get_detail_by_id(self, user_id: UUID) -> Optional[UserDetail]: ...

    async def user_profile_exists(self, user_id: UUID) -> bool: ...

    async def create_user_profile(self, user_id: UUID, first_name: str, last_name: str, preferred_name: Optional[str] = None) -> None: ...

    async def update_last_login_at(self, user_id: UUID, last_login_at) -> None: ...

    async def get_user_id_by_identity_link(self, provider: str, provider_subject: str, provider_tenant: Optional[str] = None) -> Optional[UUID]: ...

    async def upsert_identity_link(
        self, user_id: UUID, provider: str, provider_subject: str, *, provider_tenant: Optional[str] = None, additional_data: Optional[dict[str, Any]] = None
    ) -> None: ...

    async def soft_delete_identity_link(self, user_id: UUID, provider: str) -> None: ...

    async def identity_provider_is_active(self, code: str) -> bool: ...

    async def create_directory_user(
        self,
        user_id: UUID,
        email: str,
        *,
        verified: bool,
        is_active: bool,
        is_admin: bool,
        account_kind: str,
        first_name: str,
        last_name: str,
        preferred_name: Optional[str] = None,
    ) -> None: ...

    async def update_directory_user_profile(self, user_id: UUID, first_name: str, last_name: str, preferred_name: Optional[str] = None) -> None: ...

    async def update_user_active_flag(self, user_id: UUID, is_active: bool) -> None: ...

    async def create_credential(
        self, *, auth_user_id: UUID, email: str, password_hash: Optional[str], is_admin: bool, is_superuser: bool = False, verified: bool = False
    ) -> UUID:
        """Insert auth.user only (no AuthUserProfile, no app.user). password_hash may be null for passwordless End users."""
        ...


class OtpTokenPort(Protocol):
    """Ephemeral one-time passcodes keyed by email (hashed at rest), plus their per-email request quota."""

    async def store(self, email: str, code_hash: str, ttl_seconds: int) -> None: ...

    async def consume(self, email: str, code_hash: str) -> bool:
        """Return True and invalidate when the hash matches a live passcode for email."""
        ...

    async def allow_request(self, email: str, *, max_requests: int, window_seconds: int) -> bool:
        """Count this request against the email's rolling window; False once the window is exhausted."""
        ...

    async def invalidate(self, email: str) -> None:
        """Drop any live passcode for email (e.g. when its delivery failed)."""
        ...


class OtpDeliveryError(Exception):
    """The mail provider could not accept the passcode message."""


class OtpMailerPort(Protocol):
    """Deliver the plain one-time passcode out-of-band (email)."""

    async def send_otp(self, email: str, code: str, *, locale: Optional[str]) -> None:
        """Raise OtpDeliveryError when the message was not accepted for delivery."""
        ...


class GoogleIdTokenVerifierPort(Protocol):
    """Verify a Google-issued ID token (signature, issuer, expiry, audience) per ADR 0006."""

    async def verify(self, id_token: str, audiences: list[str]) -> Optional[GoogleIdentityClaims]:
        """Return verified claims, or None when the token is invalid, expired, or not issued for one of `audiences`."""
        ...


class AppleIdTokenVerifierPort(Protocol):
    """Verify an Apple-issued identity token per ADR 0008."""

    async def verify(self, id_token: str, audiences: list[str]) -> Optional[AppleIdentityClaims]:
        """Return verified claims, or None when signature, issuer, expiry, or audience is invalid."""
        ...
