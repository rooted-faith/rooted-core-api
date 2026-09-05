"""
Application-service seam: End user magic-link request / verify (stub ports).

Happy path: verify for a new email provisions passwordless credential + End user
+ Preferences and returns member tokens; verify for an existing End user returns
tokens without a password. Invalid/expired tokens are rejected.
"""

from typing import Optional
from uuid import UUID, uuid4

import pytest

from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.commands import AppMagicLinkRequestCommand, AppMagicLinkVerifyCommand
from portal.application.auth.results import MemberLoginResult, UserSensitive
from portal.domain.app.entities import EndUser, UserPreferences
from portal.exceptions.responses import UnauthorizedException


class StubPasswordProvider:
    def validate_password(self, password: str) -> bool:
        return len(password) >= 8

    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class StubUserRepository:
    def __init__(self):
        self.by_email: dict[str, UserSensitive] = {}
        self.last_login_updates: list[UUID] = []

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
        return auth_user_id

    async def get_sensitive_by_email_without_profile(self, email: str):
        return self.by_email.get(email.strip().lower())

    async def update_last_login_at(self, user_id: UUID, last_login_at) -> None:
        self.last_login_updates.append(user_id)


class StubEndUserRepository:
    def __init__(self):
        self.by_auth_user_id: dict[UUID, EndUser] = {}

    async def create_end_user(self, *, end_user_id: UUID, auth_user_id: UUID) -> EndUser:
        end_user = EndUser(id=end_user_id, auth_user_id=auth_user_id)
        self.by_auth_user_id[auth_user_id] = end_user
        return end_user

    async def get_by_auth_user_id(self, auth_user_id: UUID):
        return self.by_auth_user_id.get(auth_user_id)


class StubPreferencesRepository:
    def __init__(self):
        self.by_user_id: dict[UUID, UserPreferences] = {}

    async def create_preferences(self, preferences: UserPreferences) -> UserPreferences:
        self.by_user_id[preferences.user_id] = preferences
        return preferences

    async def get_by_user_id(self, user_id: UUID):
        return self.by_user_id.get(user_id)


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


class StubMagicLinkTokenStore:
    def __init__(self):
        self._by_email: dict[str, str] = {}

    async def store(self, email: str, token_hash: str, ttl_seconds: int) -> None:
        self._by_email[email.strip().lower()] = token_hash

    async def consume(self, email: str, token_hash: str) -> bool:
        key = email.strip().lower()
        stored = self._by_email.pop(key, None)
        return stored is not None and stored == token_hash


class StubMagicLinkMailer:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_magic_link(self, email: str, token: str) -> None:
        self.sent.append((email, token))


def _build_service() -> tuple[
    AppAuthService, StubUserRepository, StubEndUserRepository, StubPreferencesRepository, StubMagicLinkMailer, StubMagicLinkTokenStore
]:
    from portal.application.app.end_user_provisioning_service import EndUserProvisioningService

    user_repo = StubUserRepository()
    end_user_repo = StubEndUserRepository()
    prefs_repo = StubPreferencesRepository()
    password = StubPasswordProvider()
    mailer = StubMagicLinkMailer()
    token_store = StubMagicLinkTokenStore()
    provisioning = EndUserProvisioningService(
        user_repository=user_repo, end_user_repository=end_user_repo, preferences_repository=prefs_repo, password_provider=password
    )
    service = AppAuthService(
        provisioning_service=provisioning,
        user_repository=user_repo,
        end_user_repository=end_user_repo,
        preferences_repository=prefs_repo,
        magic_link_token_store=token_store,
        magic_link_mailer=mailer,
        jwt_provider=StubJwtProvider(),
        refresh_token_provider=StubRefreshTokenProvider(),
        member_refresh_app_binding_provider=StubMemberRefreshAppBindingProvider(),
        member_web_app_registry=StubMemberWebAppRegistry(),
    )
    return service, user_repo, end_user_repo, prefs_repo, mailer, token_store


async def _request_and_get_token(service: AppAuthService, mailer: StubMagicLinkMailer, email: str) -> str:
    await service.request_magic_link(AppMagicLinkRequestCommand(email=email))
    assert mailer.sent
    return mailer.sent[-1][1]


@pytest.mark.asyncio
async def test_verify_new_email_creates_passwordless_end_user_and_returns_tokens():
    service, user_repo, end_user_repo, prefs_repo, mailer, _ = _build_service()
    token = await _request_and_get_token(service, mailer, "jay@example.com")

    result = await service.verify_magic_link(AppMagicLinkVerifyCommand(email="jay@example.com", token=token))

    assert isinstance(result, MemberLoginResult)
    assert result.token.access_token == "access-token"
    assert result.token.refresh_token == "refresh-token"
    assert result.token.token_type == "bearer"
    assert result.token.expires_in > 0

    credential = user_repo.by_email["jay@example.com"]
    assert credential.password_hash is None
    assert credential.verified is True
    end_user = end_user_repo.by_auth_user_id[credential.id]
    assert result.member.id == end_user.id
    assert result.member.id != credential.id
    assert result.member.email == "jay@example.com"
    assert prefs_repo.by_user_id[end_user.id].display_name == "jay"
    assert user_repo.last_login_updates


@pytest.mark.asyncio
async def test_verify_existing_email_returns_tokens_without_password():
    service, user_repo, end_user_repo, prefs_repo, mailer, _ = _build_service()
    first_token = await _request_and_get_token(service, mailer, "jay@example.com")
    await service.verify_magic_link(AppMagicLinkVerifyCommand(email="jay@example.com", token=first_token))

    second_token = await _request_and_get_token(service, mailer, "jay@example.com")
    result = await service.verify_magic_link(AppMagicLinkVerifyCommand(email="jay@example.com", token=second_token))

    assert result.token.access_token == "access-token"
    assert result.member.email == "jay@example.com"
    end_user = next(iter(end_user_repo.by_auth_user_id.values()))
    assert result.member.id == end_user.id
    assert user_repo.by_email["jay@example.com"].password_hash is None
    assert len(prefs_repo.by_user_id) == 1


@pytest.mark.asyncio
async def test_verify_rejects_invalid_token():
    service, *_rest, mailer, _store = _build_service()
    await _request_and_get_token(service, mailer, "jay@example.com")

    with pytest.raises(UnauthorizedException):
        await service.verify_magic_link(AppMagicLinkVerifyCommand(email="jay@example.com", token="not-the-token"))


@pytest.mark.asyncio
async def test_verify_rejects_expired_or_consumed_token():
    service, *_rest, mailer, _store = _build_service()
    token = await _request_and_get_token(service, mailer, "jay@example.com")
    await service.verify_magic_link(AppMagicLinkVerifyCommand(email="jay@example.com", token=token))

    with pytest.raises(UnauthorizedException):
        await service.verify_magic_link(AppMagicLinkVerifyCommand(email="jay@example.com", token=token))


@pytest.mark.asyncio
async def test_verify_rejects_credential_without_end_user():
    service, user_repo, end_user_repo, _prefs, mailer, _store = _build_service()
    auth_user_id = uuid4()
    await user_repo.create_credential(auth_user_id=auth_user_id, email="admin-only@example.com", password_hash="hashed:Secure1!", is_admin=True, verified=True)
    token = await _request_and_get_token(service, mailer, "admin-only@example.com")

    with pytest.raises(UnauthorizedException):
        await service.verify_magic_link(AppMagicLinkVerifyCommand(email="admin-only@example.com", token=token))
    assert end_user_repo.by_auth_user_id == {}


@pytest.mark.asyncio
async def test_request_magic_link_does_not_reveal_whether_email_exists():
    service, *_rest, mailer, _store = _build_service()

    unknown = await service.request_magic_link(AppMagicLinkRequestCommand(email="unknown@example.com"))
    known_prep = await _request_and_get_token(service, mailer, "new@example.com")
    await service.verify_magic_link(AppMagicLinkVerifyCommand(email="new@example.com", token=known_prep))
    known = await service.request_magic_link(AppMagicLinkRequestCommand(email="new@example.com"))

    assert unknown.message == known.message
