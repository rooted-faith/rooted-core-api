"""
Application-service seam: End-user Google ID-token sign-in (ADR 0008, stub verifier + stub repos).

Parallel to the Admin Google tests, plus the branch the Admin flow deliberately lacks:
a first success matching nothing provisions a brand-new Auth credential + End user +
Preferences. Every rejection path fails with the same generic detail.
"""

from typing import Any, Optional
from uuid import UUID, uuid4

import pytest

from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.app_google_auth_service import GENERIC_FAILURE_DETAIL, AppGoogleAuthService
from portal.application.auth.commands import AppGoogleLoginCommand
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.results import MemberLoginResult, UserSensitive
from portal.domain.app.entities import EndUser, UserPreferences
from portal.domain.auth.entities import GoogleIdentityClaims
from portal.exceptions.responses import UnauthorizedException

ALLOWED_CLIENT_IDS = ["app-client-id"]


class StubPasswordProvider:
    def validate_password(self, password: str) -> bool:
        return len(password) >= 8

    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"


class StubUserRepository:
    """
    Models one production detail the services depend on: `get_sensitive_by_email`
    inner-joins the admin profile table, so it only ever sees credentials that have
    an AuthUserProfile row. Credentials created by End-user provisioning have none.
    """

    def __init__(self):
        self.by_email: dict[str, UserSensitive] = {}
        self.by_id: dict[UUID, UserSensitive] = {}
        self.emails_with_admin_profile: set[str] = set()
        self.identity_links: dict[tuple[str, str], UUID] = {}
        self.link_calls: list[dict[str, Any]] = []
        self.google_provider_active = True
        self.last_login_updates: list[UUID] = []

    def seed_credential(
        self, *, email: str, verified: bool = True, is_active: bool = True, is_admin: bool = False, has_admin_profile: bool = False
    ) -> UserSensitive:
        user = UserSensitive(
            id=uuid4(), email=email, password_hash=None, verified=verified, is_active=is_active, is_admin=is_admin, first_name="", last_name=""
        )
        self.by_email[email.strip().lower()] = user
        self.by_id[user.id] = user
        if has_admin_profile:
            self.emails_with_admin_profile.add(email.strip().lower())
        return user

    async def create_credential(
        self, *, auth_user_id: UUID, email: str, password_hash: Optional[str], is_admin: bool, is_superuser: bool = False, verified: bool = False
    ) -> UUID:
        user = UserSensitive(
            id=auth_user_id,
            email=email,
            password_hash=password_hash,
            verified=verified,
            is_active=True,
            is_admin=is_admin,
            is_superuser=is_superuser,
            first_name="",
            last_name="",
        )
        self.by_email[email] = user
        self.by_id[auth_user_id] = user
        return auth_user_id

    async def identity_provider_is_active(self, code: str) -> bool:
        assert code == "google"
        return self.google_provider_active

    async def get_user_id_by_identity_link(self, provider: str, provider_subject: str, provider_tenant: Optional[str] = None) -> Optional[UUID]:
        return self.identity_links.get((provider, provider_subject))

    async def upsert_identity_link(
        self, user_id: UUID, provider: str, provider_subject: str, *, provider_tenant: Optional[str] = None, additional_data: Optional[dict[str, Any]] = None
    ) -> None:
        self.link_calls.append({"user_id": user_id, "provider": provider, "provider_subject": provider_subject, "additional_data": additional_data})
        self.identity_links[(provider, provider_subject)] = user_id

    async def get_sensitive_by_email(self, email: str) -> Optional[UserSensitive]:
        key = email.strip().lower()
        if key not in self.emails_with_admin_profile:
            return None  # inner join on AuthUserProfile drops profile-less End user credentials
        return self.by_email.get(key)

    async def get_sensitive_by_email_without_profile(self, email: str) -> Optional[UserSensitive]:
        return self.by_email.get(email.strip().lower())

    async def get_sensitive_by_id(self, user_id: UUID) -> Optional[UserSensitive]:
        return self.by_id.get(user_id)

    async def update_last_login_at(self, user_id: UUID, last_login_at) -> None:
        self.last_login_updates.append(user_id)


class StubEndUserRepository:
    def __init__(self):
        self.by_auth_user_id: dict[UUID, EndUser] = {}

    def seed(self, auth_user_id: UUID) -> EndUser:
        end_user = EndUser(id=uuid4(), auth_user_id=auth_user_id)
        self.by_auth_user_id[auth_user_id] = end_user
        return end_user

    async def create_end_user(self, *, end_user_id: UUID, auth_user_id: UUID) -> EndUser:
        end_user = EndUser(id=end_user_id, auth_user_id=auth_user_id)
        self.by_auth_user_id[auth_user_id] = end_user
        return end_user

    async def get_by_auth_user_id(self, auth_user_id: UUID):
        return self.by_auth_user_id.get(auth_user_id)

    async def get_by_id(self, end_user_id: UUID):
        return next((end_user for end_user in self.by_auth_user_id.values() if end_user.id == end_user_id), None)


class StubPreferencesRepository:
    def __init__(self):
        self.by_user_id: dict[UUID, UserPreferences] = {}

    async def create_preferences(self, preferences: UserPreferences) -> UserPreferences:
        self.by_user_id[preferences.user_id] = preferences
        return preferences

    async def get_by_user_id(self, user_id: UUID):
        return self.by_user_id.get(user_id)


class StubGoogleIdTokenVerifier:
    def __init__(self):
        self.claims_by_token: dict[str, GoogleIdentityClaims] = {}

    def register(self, token: str, claims: GoogleIdentityClaims) -> None:
        self.claims_by_token[token] = claims

    async def verify(self, id_token: str, audiences: list[str]) -> Optional[GoogleIdentityClaims]:
        claims = self.claims_by_token.get(id_token)
        if not claims or claims.audience not in audiences:
            return None
        return claims


class StubJwtProvider:
    def create_access_token(self, *args, **kwargs) -> str:
        return "access-token"


class StubRefreshTokenProvider:
    async def issue(self, *, user_id: UUID, device_id: UUID, family_id: UUID) -> str:
        return "refresh-token"


class StubMemberRefreshAppBindingProvider:
    def __init__(self):
        self.bound: list[tuple] = []

    async def bind(self, family_id: UUID, app_code: str) -> None:
        self.bound.append((family_id, app_code))


class StubMemberWebAppRegistry:
    def __init__(self, default_code: str = "rooted-app"):
        self._default_code = default_code

    @property
    def default_app_code(self) -> str:
        return self._default_code

    def resolve_app_code(self, origin=None, referer=None):
        return None


def _build_service(
    monkeypatch: pytest.MonkeyPatch, client_ids: list[str] = ALLOWED_CLIENT_IDS
) -> tuple[AppGoogleAuthService, StubUserRepository, StubEndUserRepository, StubPreferencesRepository, StubGoogleIdTokenVerifier]:
    from portal.config import settings

    monkeypatch.setattr(settings, "GOOGLE_APP_CLIENT_IDS", ",".join(client_ids))

    user_repo = StubUserRepository()
    end_user_repo = StubEndUserRepository()
    prefs_repo = StubPreferencesRepository()
    verifier = StubGoogleIdTokenVerifier()
    provisioning = EndUserProvisioningService(
        user_repository=user_repo, end_user_repository=end_user_repo, preferences_repository=prefs_repo, password_provider=StubPasswordProvider()
    )
    member_login_service = MemberLoginService(
        user_repository=user_repo,
        preferences_repository=prefs_repo,
        jwt_provider=StubJwtProvider(),
        refresh_token_provider=StubRefreshTokenProvider(),
        member_refresh_app_binding_provider=StubMemberRefreshAppBindingProvider(),
        member_web_app_registry=StubMemberWebAppRegistry(),
    )
    service = AppGoogleAuthService(
        provisioning_service=provisioning,
        user_repository=user_repo,
        end_user_repository=end_user_repo,
        google_id_token_verifier=verifier,
        member_login_service=member_login_service,
    )
    return service, user_repo, end_user_repo, prefs_repo, verifier


def _claims(subject: str = "google-sub-1", email: str = "jay@example.com", email_verified: bool = True, audience: str = "app-client-id"):
    return GoogleIdentityClaims(subject=subject, email=email, email_verified=email_verified, audience=audience)


@pytest.mark.asyncio
async def test_first_success_provisions_a_brand_new_account_and_links_it(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, prefs_repo, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims(email="Jay@Example.com"))

    result = await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))

    assert isinstance(result, MemberLoginResult)
    credential = user_repo.by_email["jay@example.com"]
    assert credential.password_hash is None
    assert credential.verified is True
    end_user = end_user_repo.by_auth_user_id[credential.id]
    assert result.member.id == end_user.id
    assert result.member.id != credential.id
    assert prefs_repo.by_user_id[end_user.id].display_name == "jay"
    assert user_repo.link_calls == [
        {"user_id": credential.id, "provider": "google", "provider_subject": "google-sub-1", "additional_data": {"email": "Jay@Example.com"}}
    ]
    assert result.token.access_token == "access-token"
    assert result.token.refresh_token == "refresh-token"


@pytest.mark.asyncio
async def test_later_success_resolves_by_subject_without_provisioning_again(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims())
    first = await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))

    # Remove the email match path entirely — only the Identity link should resolve the account now.
    user_repo.by_email.clear()
    verifier.register("token-2", _claims())

    second = await service.login_with_google(AppGoogleLoginCommand(id_token="token-2"))

    assert second.member.id == first.member.id
    assert len(end_user_repo.by_auth_user_id) == 1
    assert len(user_repo.link_calls) == 1  # no re-upsert needed on subject-match path


@pytest.mark.asyncio
async def test_verified_email_matches_an_existing_end_user_and_upserts_the_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    credential = user_repo.seed_credential(email="jay@example.com")
    end_user = end_user_repo.seed(credential.id)
    verifier.register("token-1", _claims(email="JAY@example.com"))

    result = await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))

    assert result.member.id == end_user.id
    assert len(end_user_repo.by_auth_user_id) == 1  # matched, never duplicated
    assert user_repo.link_calls[0]["user_id"] == credential.id


@pytest.mark.asyncio
async def test_matches_an_otp_provisioned_account_which_has_no_admin_profile_row(monkeypatch: pytest.MonkeyPatch):
    """
    Parent story 8: a later Google sign-in with the same verified email must land on the
    existing account, not a duplicate. End-user credentials have no AuthUserProfile row,
    so the email lookup must not be the profile-joining one.
    """
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    credential = user_repo.seed_credential(email="jay@example.com")  # no admin profile, as OTP provisioning leaves it
    end_user = end_user_repo.seed(credential.id)
    verifier.register("token-1", _claims())

    result = await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))

    assert result.member.id == end_user.id
    assert len(end_user_repo.by_auth_user_id) == 1
    assert len(user_repo.by_email) == 1  # no second credential created


@pytest.mark.asyncio
async def test_rejects_when_provider_inactive(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, _end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    user_repo.google_provider_active = False
    verifier.register("token-1", _claims())

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_when_client_id_allowlist_empty(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch, client_ids=[])
    verifier.register("token-1", _claims())

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert end_user_repo.by_auth_user_id == {}


@pytest.mark.asyncio
async def test_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch):
    service, _user_repo, end_user_repo, _prefs, _verifier = _build_service(monkeypatch)

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="not-a-registered-token"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert end_user_repo.by_auth_user_id == {}


@pytest.mark.asyncio
async def test_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch):
    service, _user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims(audience="other-client-id"))

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert end_user_repo.by_auth_user_id == {}


@pytest.mark.asyncio
async def test_rejects_unverified_email_and_never_provisions(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims(email_verified=False))

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert end_user_repo.by_auth_user_id == {}
    assert user_repo.by_email == {}


@pytest.mark.asyncio
async def test_rejects_inactive_credential_and_does_not_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    credential = user_repo.seed_credential(email="jay@example.com", is_active=False)
    end_user_repo.seed(credential.id)
    verifier.register("token-1", _claims())

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_admin_only_credential_without_an_end_user(monkeypatch: pytest.MonkeyPatch):
    """An admin console credential has no app.user row; Google app sign-in must not attach product identity to it."""
    service, user_repo, _end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    user_repo.seed_credential(email="admin-only@example.com", is_admin=True, has_admin_profile=True)
    verifier.register("token-1", _claims(email="admin-only@example.com"))

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_linked_subject_whose_credential_was_deactivated(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, _end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims())
    await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))

    user_repo.by_id[user_repo.link_calls[0]["user_id"]].is_active = False

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AppGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
