"""
Application-service seam: End user email-OTP request / verify (stub ports, ADR 0008).

Happy path: verify for a new email provisions passwordless credential + End user
+ Preferences and returns member tokens; verify for an existing End user returns
tokens without a password. Wrong/expired/consumed codes are rejected with one
generic failure, and repeated requests for the same email are throttled.
"""

from typing import Optional
from uuid import UUID, uuid4

import pytest

from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.commands import AppOtpRequestCommand, AppOtpVerifyCommand
from portal.application.auth.mappers import member_login_result_to_api
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.results import MemberLoginResult, UserSensitive
from portal.domain.app.entities import EndUser, UserPreferences
from portal.exceptions.responses import TooManyRequestsException, UnauthorizedException


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


class StubOtpTokenStore:
    def __init__(self):
        self.code_hash_by_email: dict[str, str] = {}
        self.requests_by_email: dict[str, int] = {}
        self.quota_calls: list[tuple[str, int, int]] = []
        self.allow_requests = True

    async def store(self, email: str, code_hash: str, ttl_seconds: int) -> None:
        self.code_hash_by_email[email.strip().lower()] = code_hash

    async def consume(self, email: str, code_hash: str) -> bool:
        key = email.strip().lower()
        stored = self.code_hash_by_email.pop(key, None)
        return stored is not None and stored == code_hash

    async def allow_request(self, email: str, *, max_requests: int, window_seconds: int) -> bool:
        key = email.strip().lower()
        self.quota_calls.append((key, max_requests, window_seconds))
        self.requests_by_email[key] = self.requests_by_email.get(key, 0) + 1
        if not self.allow_requests:
            return False
        return self.requests_by_email[key] <= max_requests


class StubOtpMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, Optional[str]]] = []

    async def send_otp(self, email: str, code: str, *, locale: Optional[str]) -> None:
        self.sent.append((email, code, locale))


def _build_service() -> tuple[AppAuthService, StubUserRepository, StubEndUserRepository, StubPreferencesRepository, StubOtpMailer, StubOtpTokenStore]:
    from portal.application.app.end_user_provisioning_service import EndUserProvisioningService

    user_repo = StubUserRepository()
    end_user_repo = StubEndUserRepository()
    prefs_repo = StubPreferencesRepository()
    password = StubPasswordProvider()
    mailer = StubOtpMailer()
    token_store = StubOtpTokenStore()
    provisioning = EndUserProvisioningService(
        user_repository=user_repo, end_user_repository=end_user_repo, preferences_repository=prefs_repo, password_provider=password
    )
    member_login_service = MemberLoginService(
        user_repository=user_repo,
        preferences_repository=prefs_repo,
        jwt_provider=StubJwtProvider(),
        refresh_token_provider=StubRefreshTokenProvider(),
        member_refresh_app_binding_provider=StubMemberRefreshAppBindingProvider(),
        member_web_app_registry=StubMemberWebAppRegistry(),
    )
    service = AppAuthService(
        provisioning_service=provisioning,
        user_repository=user_repo,
        end_user_repository=end_user_repo,
        otp_token_store=token_store,
        otp_mailer=mailer,
        member_login_service=member_login_service,
    )
    return service, user_repo, end_user_repo, prefs_repo, mailer, token_store


async def _request_and_get_code(service: AppAuthService, mailer: StubOtpMailer, email: str) -> str:
    await service.request_otp(AppOtpRequestCommand(email=email))
    assert mailer.sent
    return mailer.sent[-1][1]


@pytest.mark.asyncio
async def test_requested_code_is_six_digits_and_never_returned_to_the_caller():
    service, *_rest, mailer, token_store = _build_service()

    result = await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    code = mailer.sent[-1][1]
    assert len(code) == 6 and code.isdigit()
    assert code not in result.message
    # only the hash is ever handed to the store
    assert code not in token_store.code_hash_by_email["jay@example.com"]


@pytest.mark.asyncio
async def test_verify_new_email_creates_passwordless_end_user_and_returns_tokens():
    service, user_repo, end_user_repo, prefs_repo, mailer, _ = _build_service()
    code = await _request_and_get_code(service, mailer, "jay@example.com")

    result = await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code=code))

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
    assert set(member_login_result_to_api(result).member.model_dump(by_alias=True)) == {
        "id",
        "email",
        "first_name",
        "last_name",
        "preferredName",
        "roles",
        "preferredLocaleId",
        "last_login_at",
    }
    assert prefs_repo.by_user_id[end_user.id].display_name == "jay"
    assert user_repo.last_login_updates


@pytest.mark.asyncio
async def test_verify_existing_email_returns_tokens_without_password():
    service, user_repo, end_user_repo, prefs_repo, mailer, _ = _build_service()
    first_code = await _request_and_get_code(service, mailer, "jay@example.com")
    await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code=first_code))

    second_code = await _request_and_get_code(service, mailer, "jay@example.com")
    result = await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code=second_code))

    assert result.token.access_token == "access-token"
    assert result.member.email == "jay@example.com"
    end_user = next(iter(end_user_repo.by_auth_user_id.values()))
    assert result.member.id == end_user.id
    assert user_repo.by_email["jay@example.com"].password_hash is None
    assert len(prefs_repo.by_user_id) == 1


@pytest.mark.asyncio
async def test_verify_rejects_wrong_code():
    service, *_rest, mailer, _store = _build_service()
    await _request_and_get_code(service, mailer, "jay@example.com")

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code="000000"))


@pytest.mark.asyncio
async def test_verify_rejects_expired_or_consumed_code():
    service, *_rest, mailer, _store = _build_service()
    code = await _request_and_get_code(service, mailer, "jay@example.com")
    await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code=code))

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code=code))


@pytest.mark.asyncio
async def test_every_verify_rejection_shares_one_generic_detail():
    service, user_repo, _end_user_repo, _prefs, mailer, _store = _build_service()
    await user_repo.create_credential(auth_user_id=uuid4(), email="admin-only@example.com", password_hash="hashed:Secure1!", is_admin=True, verified=True)

    await _request_and_get_code(service, mailer, "jay@example.com")
    with pytest.raises(UnauthorizedException) as wrong_code:
        await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code="000000"))

    credential_code = await _request_and_get_code(service, mailer, "admin-only@example.com")
    with pytest.raises(UnauthorizedException) as no_end_user:
        await service.verify_otp(AppOtpVerifyCommand(email="admin-only@example.com", code=credential_code))

    assert wrong_code.value.detail == no_end_user.value.detail


@pytest.mark.asyncio
async def test_verify_rejects_credential_without_end_user():
    service, user_repo, end_user_repo, _prefs, mailer, _store = _build_service()
    auth_user_id = uuid4()
    await user_repo.create_credential(auth_user_id=auth_user_id, email="admin-only@example.com", password_hash="hashed:Secure1!", is_admin=True, verified=True)
    code = await _request_and_get_code(service, mailer, "admin-only@example.com")

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email="admin-only@example.com", code=code))
    assert end_user_repo.by_auth_user_id == {}


@pytest.mark.asyncio
async def test_request_otp_does_not_reveal_whether_email_exists():
    service, *_rest, mailer, _store = _build_service()

    unknown = await service.request_otp(AppOtpRequestCommand(email="unknown@example.com"))
    known_prep = await _request_and_get_code(service, mailer, "new@example.com")
    await service.verify_otp(AppOtpVerifyCommand(email="new@example.com", code=known_prep))
    known = await service.request_otp(AppOtpRequestCommand(email="new@example.com"))

    assert unknown.message == known.message


@pytest.mark.asyncio
async def test_request_otp_is_rate_limited_per_email():
    from portal.config import settings

    service, *_rest, _mailer, token_store = _build_service()

    for _ in range(settings.OTP_REQUEST_MAX_PER_WINDOW):
        await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    with pytest.raises(TooManyRequestsException):
        await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    # a different email is unaffected by the exhausted window
    await service.request_otp(AppOtpRequestCommand(email="other@example.com"))
    assert token_store.quota_calls[0][1:] == (settings.OTP_REQUEST_MAX_PER_WINDOW, settings.OTP_REQUEST_WINDOW_SECONDS)


@pytest.mark.asyncio
async def test_throttled_request_does_not_issue_or_store_a_code():
    service, *_rest, mailer, token_store = _build_service()
    token_store.allow_requests = False

    with pytest.raises(TooManyRequestsException):
        await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    assert mailer.sent == []
    assert token_store.code_hash_by_email == {}


@pytest.mark.asyncio
async def test_otp_email_uses_the_locale_resolved_for_this_request(monkeypatch: pytest.MonkeyPatch):
    import portal.application.auth.app_auth_service as service_module

    service, *_rest, mailer, _store = _build_service()
    monkeypatch.setattr(service_module, "get_resolved_locale_code", lambda: "en")

    await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    assert mailer.sent[-1][2] == "en"
