"""
Application-service seam: End user register / login (stub ports).

Happy path: register provisions credential + End user + Preferences and
returns member tokens; login authenticates an existing End user.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.commands import AppLoginCommand, AppRegisterCommand
from portal.application.auth.results import MemberLoginResult, TokenResult, UserSensitive
from portal.domain.app.entities import EndUser, UserPreferences
from portal.exceptions.responses import BadRequestException, UnauthorizedException


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
        self, *, auth_user_id: UUID, email: str, password_hash: str, is_admin: bool, is_superuser: bool = False, verified: bool = False
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


def _build_service() -> tuple[AppAuthService, StubUserRepository, StubEndUserRepository, StubPreferencesRepository]:
    from portal.application.app.end_user_provisioning_service import EndUserProvisioningService

    user_repo = StubUserRepository()
    end_user_repo = StubEndUserRepository()
    prefs_repo = StubPreferencesRepository()
    password = StubPasswordProvider()
    provisioning = EndUserProvisioningService(
        user_repository=user_repo, end_user_repository=end_user_repo, preferences_repository=prefs_repo, password_provider=password
    )
    service = AppAuthService(
        provisioning_service=provisioning,
        user_repository=user_repo,
        end_user_repository=end_user_repo,
        preferences_repository=prefs_repo,
        password_provider=password,
        jwt_provider=StubJwtProvider(),
        refresh_token_provider=StubRefreshTokenProvider(),
        member_refresh_app_binding_provider=StubMemberRefreshAppBindingProvider(),
        member_web_app_registry=StubMemberWebAppRegistry(),
    )
    return service, user_repo, end_user_repo, prefs_repo


@pytest.mark.asyncio
async def test_register_creates_end_user_and_returns_tokens():
    service, user_repo, end_user_repo, prefs_repo = _build_service()

    result = await service.register(AppRegisterCommand(email="jay@example.com", password="Secure1!", display_name="Jay"))

    assert isinstance(result, MemberLoginResult)
    assert result.token.access_token == "access-token"
    assert result.token.refresh_token == "refresh-token"
    assert result.token.token_type == "bearer"
    assert result.token.expires_in > 0

    assert "jay@example.com" in user_repo.by_email
    assert user_repo.by_email["jay@example.com"].verified is True
    end_user = end_user_repo.by_auth_user_id[user_repo.by_email["jay@example.com"].id]
    assert result.member.id == end_user.id
    assert result.member.id != user_repo.by_email["jay@example.com"].id
    assert result.member.email == "jay@example.com"
    assert result.member.preferred_name == "Jay"
    assert prefs_repo.by_user_id[end_user.id].display_name == "Jay"


@pytest.mark.asyncio
async def test_login_returns_tokens_for_existing_end_user():
    service, user_repo, end_user_repo, prefs_repo = _build_service()
    await service.register(AppRegisterCommand(email="jay@example.com", password="Secure1!", display_name="Jay"))

    result = await service.login(AppLoginCommand(email="jay@example.com", password="Secure1!"))

    assert result.token.access_token == "access-token"
    assert result.member.email == "jay@example.com"
    assert result.member.preferred_name == "Jay"
    end_user = next(iter(end_user_repo.by_auth_user_id.values()))
    assert result.member.id == end_user.id
    assert user_repo.last_login_updates


@pytest.mark.asyncio
async def test_login_rejects_wrong_password():
    service, *_ = _build_service()
    await service.register(AppRegisterCommand(email="jay@example.com", password="Secure1!", display_name="Jay"))

    with pytest.raises(UnauthorizedException):
        await service.login(AppLoginCommand(email="jay@example.com", password="WrongPass1"))


@pytest.mark.asyncio
async def test_login_rejects_credential_without_end_user():
    service, user_repo, end_user_repo, _ = _build_service()
    auth_user_id = uuid4()
    await user_repo.create_credential(auth_user_id=auth_user_id, email="admin-only@example.com", password_hash="hashed:Secure1!", is_admin=True, verified=True)

    with pytest.raises(UnauthorizedException):
        await service.login(AppLoginCommand(email="admin-only@example.com", password="Secure1!"))
    assert end_user_repo.by_auth_user_id == {}


@pytest.mark.asyncio
async def test_register_rejects_weak_password():
    service, *_ = _build_service()

    with pytest.raises(BadRequestException):
        await service.register(AppRegisterCommand(email="jay@example.com", password="short", display_name="Jay"))
