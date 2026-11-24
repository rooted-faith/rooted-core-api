"""
Application-service seam: End user email-OTP request / verify (stub ports, ADR 0008).

Happy path: verify for a new email provisions passwordless credential + End user
+ Preferences and returns member tokens; verify for an existing End user returns
tokens without a password. Wrong/expired/consumed codes are rejected with one
generic failure, and repeated requests for the same email are throttled.
"""

import asyncio
from typing import Optional
from uuid import UUID, uuid4

import pytest

from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.commands import AppOtpRequestCommand, AppOtpVerifyCommand
from portal.application.auth.mappers import member_login_result_to_api
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.otp_test_passcode_service import OtpTestPasscodeService
from portal.application.auth.results import MemberLoginResult, UserSensitive
from portal.config import Configuration, settings
from portal.domain.app.entities import EndUser, UserPreferences
from portal.domain.auth.constants import OtpDeliveryMode
from portal.domain.auth.entities import OtpChallenge
from portal.domain.auth.otp_test_policy import OtpTestPolicy
from portal.domain.auth.ports import OtpDeliveryError
from portal.exceptions.responses import ApiBaseException, TooManyRequestsException, UnauthorizedException


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


class StubBibleRepository:
    async def youversion_bible_id_is_active(self, youversion_bible_id: str) -> bool:
        return youversion_bible_id in {"113", "1392", "36"}


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
        self.challenges: dict[str, OtpChallenge] = {}
        self.ttl_by_email: dict[str, int] = {}
        self.requests_by_email: dict[str, int] = {}
        self.quota_calls: list[tuple[str, int, int]] = []
        self.allow_requests = True

    async def store(self, email: str, challenge: OtpChallenge, ttl_seconds: int) -> None:
        self.challenges[email] = challenge
        self.ttl_by_email[email] = ttl_seconds

    async def get(self, email: str) -> Optional[OtpChallenge]:
        return self.challenges.get(email)

    async def list_fixed(self) -> list[tuple[str, OtpChallenge]]:
        return [(email, challenge) for email, challenge in self.challenges.items() if challenge.delivery_mode is OtpDeliveryMode.FIXED]

    async def consume(self, email: str, challenge: OtpChallenge) -> bool:
        if self.challenges.get(email) != challenge:
            return False
        del self.challenges[email]
        return True

    async def allow_request(self, email: str, *, max_requests: int, window_seconds: int) -> bool:
        key = email.strip().lower()
        self.quota_calls.append((key, max_requests, window_seconds))
        self.requests_by_email[key] = self.requests_by_email.get(key, 0) + 1
        if not self.allow_requests:
            return False
        return self.requests_by_email[key] <= max_requests


class StubOtpTestPolicySource:
    """Controls what the backend currently observes from the Firebase server template."""

    def __init__(self, policy: Optional[OtpTestPolicy] = None):
        self.policy = policy
        self.reads = 0

    async def current(self) -> Optional[OtpTestPolicy]:
        self.reads += 1
        return self.policy


class StubOtpMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, Optional[str]]] = []
        self.fail = False

    async def send_otp(self, email: str, code: str, *, locale: Optional[str]) -> None:
        if self.fail:
            raise OtpDeliveryError("provider down")
        self.sent.append((email, code, locale))


def _build_service(
    policy_source: Optional[StubOtpTestPolicySource] = None, token_store=None
) -> tuple[AppAuthService, StubUserRepository, StubEndUserRepository, StubPreferencesRepository, StubOtpMailer, StubOtpTokenStore]:
    from portal.application.app.end_user_provisioning_service import EndUserProvisioningService

    user_repo = StubUserRepository()
    end_user_repo = StubEndUserRepository()
    prefs_repo = StubPreferencesRepository()
    password = StubPasswordProvider()
    mailer = StubOtpMailer()
    token_store = token_store or StubOtpTokenStore()
    provisioning = EndUserProvisioningService(
        user_repository=user_repo,
        end_user_repository=end_user_repo,
        preferences_repository=prefs_repo,
        bible_repository=StubBibleRepository(),
        password_provider=password,
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
        otp_test_passcode_service=OtpTestPasscodeService(otp_test_policy=policy_source or StubOtpTestPolicySource(), otp_token_store=token_store),
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
    assert code not in token_store.challenges["jay@example.com"].code_hash


@pytest.mark.asyncio
async def test_verify_new_email_creates_passwordless_end_user_and_returns_tokens(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("portal.application.auth.app_auth_service.get_resolved_locale_code", lambda: "zh-TW")
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
    assert prefs_repo.by_user_id[end_user.id].bible_version == "1392"
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
    assert token_store.challenges == {}


@pytest.mark.asyncio
async def test_otp_email_uses_the_locale_resolved_for_this_request(monkeypatch: pytest.MonkeyPatch):
    import portal.application.auth.app_auth_service as service_module

    service, *_rest, mailer, _store = _build_service()
    monkeypatch.setattr(service_module, "get_resolved_locale_code", lambda: "en")

    await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    assert mailer.sent[-1][2] == "en"


@pytest.mark.asyncio
async def test_delivery_failure_invalidates_the_code_and_returns_retryable_503():
    service, *_rest, mailer, token_store = _build_service()
    mailer.fail = True

    with pytest.raises(ApiBaseException) as failure:
        await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    assert failure.value.status_code == 503
    assert token_store.challenges == {}


@pytest.mark.asyncio
async def test_delivery_failure_detail_is_identical_for_known_and_unknown_emails():
    service, *_rest, mailer, _store = _build_service()
    code = await _request_and_get_code(service, mailer, "known@example.com")
    await service.verify_otp(AppOtpVerifyCommand(email="known@example.com", code=code))
    mailer.fail = True

    with pytest.raises(ApiBaseException) as known:
        await service.request_otp(AppOtpRequestCommand(email="known@example.com"))
    with pytest.raises(ApiBaseException) as unknown:
        await service.request_otp(AppOtpRequestCommand(email="unknown@example.com"))

    assert known.value.status_code == unknown.value.status_code == 503
    assert known.value.detail == unknown.value.detail


TESTER = "alice@test.example.com"


def _enabled_policy(*rules: str, project_id: str = "rooted-app-dev") -> OtpTestPolicy:
    return OtpTestPolicy(project_id=project_id, test_mode_enabled=True, allowlist=rules or ("*@test.example.com",))


@pytest.fixture
def stg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENV", "stg")
    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "")


@pytest.mark.asyncio
async def test_eligible_tester_gets_a_fixed_challenge_without_email_and_signs_in_once(stg):
    service, user_repo, end_user_repo, prefs_repo, mailer, token_store = _build_service(StubOtpTestPolicySource(_enabled_policy()))

    acknowledgement = await service.request_otp(AppOtpRequestCommand(email=" Alice@Test.Example.com "))

    assert acknowledgement.delivery_mode is OtpDeliveryMode.FIXED
    assert "sent" not in acknowledgement.message
    assert "123456" not in acknowledgement.message
    assert mailer.sent == []
    assert "123456" not in token_store.challenges[TESTER].code_hash
    assert token_store.ttl_by_email[TESTER] == settings.OTP_CODE_EXPIRE_MINUTES * 60

    result = await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))

    assert result.member.email == TESTER
    credential = user_repo.by_email[TESTER]
    assert credential.is_admin is False and credential.is_superuser is False
    assert end_user_repo.by_auth_user_id[credential.id].id in prefs_repo.by_user_id
    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))


async def _selected_mode(policy: Optional[OtpTestPolicy], email: str) -> OtpDeliveryMode:
    service, *_rest, mailer, _store = _build_service(StubOtpTestPolicySource(policy))
    result = await service.request_otp(AppOtpRequestCommand(email=email))
    assert bool(mailer.sent) is (result.delivery_mode is OtpDeliveryMode.EMAIL)
    return result.delivery_mode


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["dev", "stg"])
async def test_recognized_test_environments_allow_test_passcodes(stg, monkeypatch: pytest.MonkeyPatch, environment: str):
    monkeypatch.setattr(settings, "ENV", environment)

    assert await _selected_mode(_enabled_policy(), TESTER) is OtpDeliveryMode.FIXED


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["prod", "PROD", "production", "DEV", "STG", " stg", "staging", "test", "local", ""])
async def test_production_and_unrecognized_environments_never_consult_the_remote_policy(stg, monkeypatch: pytest.MonkeyPatch, environment: str):
    monkeypatch.setattr(settings, "ENV", environment)
    source = StubOtpTestPolicySource(_enabled_policy())
    service, *_rest, mailer, _store = _build_service(source)

    result = await service.request_otp(AppOtpRequestCommand(email=TESTER))

    assert result.delivery_mode is OtpDeliveryMode.EMAIL
    assert len(mailer.sent) == 1
    assert source.reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", ["rooted-app-prod", "rooted-app-dev-2", "Rooted-App-Dev", ""])
async def test_wrong_firebase_project_selects_email(stg, project_id: str):
    assert await _selected_mode(_enabled_policy(project_id=project_id), TESTER) is OtpDeliveryMode.EMAIL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [
        None,
        OtpTestPolicy(project_id="rooted-app-dev"),
        OtpTestPolicy(project_id="rooted-app-dev", test_mode_enabled=False, allowlist=("*@test.example.com",)),
        OtpTestPolicy(project_id="rooted-app-dev", test_mode_enabled=True, allowlist=()),
    ],
    ids=["unusable", "defaults", "disabled", "empty-allowlist"],
)
async def test_unusable_disabled_or_empty_policy_selects_email(stg, policy: Optional[OtpTestPolicy]):
    assert await _selected_mode(policy, TESTER) is OtpDeliveryMode.EMAIL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rule", "email", "expected"),
    [
        ("tester@example.com", "tester@example.com", "fixed"),
        ("  Tester@Example.COM ", " TESTER@example.com ", "fixed"),
        ("tester@example.com", "tester+qa@example.com", "email"),
        ("tester@example.com", "test.er@example.com", "email"),
        ("tester@example.com", "other@example.com", "email"),
        ("tester+qa@example.com", "tester+qa@example.com", "fixed"),
        ("*@test.example.com", "alice@test.example.com", "fixed"),
        ("*@test.example.com", "alice@a.test.example.com", "email"),
        ("*@test.example.com", "alice@test.example.com.attacker.com", "email"),
        ("*@test.example.com", "alice@eviltest.example.com", "email"),
        ("*@test.example.com", "alice@example.com", "email"),
        ("*@*.example.com", "alice@a.example.com", "fixed"),
        ("*@*.example.com", "alice@a.b.example.com", "fixed"),
        ("*@*.example.com", "alice@example.com", "email"),
        ("*@*.example.com", "alice@evil-example.com", "email"),
        ("*@*.example.com", "alice@example.com.attacker.com", "email"),
        ("*@*.example.com", "alice@.example.com", "email"),
        ("*@*.example.com", "alice@a@b.example.com", "email"),
    ],
)
async def test_allowlist_rules_match_complete_identities_only(stg, rule: str, email: str, expected: str):
    assert (await _selected_mode(_enabled_policy(rule), email)).value == expected


@pytest.mark.asyncio
async def test_any_matching_rule_is_enough_and_duplicates_change_nothing(stg):
    policy = _enabled_policy("other@example.com", "*@test.example.com", "*@test.example.com")

    assert await _selected_mode(policy, TESTER) is OtpDeliveryMode.FIXED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_rule",
    [
        "",
        "   ",
        "*",
        "**",
        "*@*",
        "*@**.example.com",
        "*@*.*.example.com",
        "*@com",
        "*@*.com",
        "a*@example.com",
        "*a@example.com",
        "*@test*.example.com",
        "*@.example.com",
        "*@example..com",
        "*@example.com.",
        "*@-example.com",
        "tester?@example.com",
        "tester[12]@example.com",
        "tester{1,2}@example.com",
        "tester\\@example.com",
        "^tester@example.com$",
        ".*@example.com",
        "tester@example",
        "tester@@example.com",
        "@example.com",
        "tester@",
        "example.com",
        "te ster@example.com",
        "tester@example.com\n*@example.com",
        "tester@example.com,other@example.com",
    ],
)
async def test_one_invalid_rule_disables_the_entire_allowlist(stg, invalid_rule: str):
    assert await _selected_mode(_enabled_policy("*@test.example.com", invalid_rule), TESTER) is OtpDeliveryMode.EMAIL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "accepted"),
    [
        ("", "123456"),
        ("012345", "012345"),
        ("000000", "000000"),
        ("12345", "123456"),
        ("1234567", "123456"),
        ("12345a", "123456"),
        (" 654321", "123456"),
        ("654321\n", "123456"),
        ("٦٥٤٣٢١", "123456"),
    ],
)
async def test_only_a_six_ascii_digit_override_replaces_the_default_test_passcode(
    stg, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, override: str, accepted: str
):
    monkeypatch.setattr(settings, "OTP_FIXED_CODE", override)
    service, *_rest, mailer, _store = _build_service(StubOtpTestPolicySource(_enabled_policy()))

    result = await service.request_otp(AppOtpRequestCommand(email=TESTER))

    assert result.delivery_mode is OtpDeliveryMode.FIXED
    assert mailer.sent == []
    if override != accepted:
        assert "OTP_FIXED_CODE" in caplog.text
        assert "123456" not in caplog.text
        assert not override.strip() or override.strip() not in caplog.text
    if override.strip() and override != accepted:
        with pytest.raises(UnauthorizedException):
            await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code=override))
    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code=accepted))).member.email == TESTER


@pytest.mark.asyncio
async def test_logs_never_expose_codes_or_the_allowlist(stg, caplog: pytest.LogCaptureFixture):
    caplog.set_level("DEBUG")
    service, *_rest, mailer, _store = _build_service(StubOtpTestPolicySource(_enabled_policy("*@test.example.com", "secret-tester@example.com")))

    await service.request_otp(AppOtpRequestCommand(email=TESTER))
    await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))
    emailed_code = await _request_and_get_code(service, mailer, "jay@example.com")
    await service.verify_otp(AppOtpVerifyCommand(email="jay@example.com", code=emailed_code))

    assert "123456" not in caplog.text
    assert emailed_code not in caplog.text
    assert "secret-tester" not in caplog.text


@pytest.mark.asyncio
async def test_fixed_code_needs_a_prior_request_and_belongs_to_one_email(stg):
    service, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()))
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email="bob@test.example.com", code="123456"))


@pytest.mark.asyncio
async def test_returning_tester_can_repeat_the_same_code_after_a_new_request(stg):
    service, _users, end_user_repo, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()))

    for _ in range(2):
        await service.request_otp(AppOtpRequestCommand(email=TESTER))
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))

    assert len(end_user_repo.by_auth_user_id) == 1


@pytest.mark.asyncio
async def test_wrong_code_does_not_consume_the_fixed_challenge(stg):
    service, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()))
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="999999"))

    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))).member.email == TESTER


@pytest.mark.asyncio
async def test_fixed_mode_respects_the_request_quota(stg):
    service, *_rest, token_store = _build_service(StubOtpTestPolicySource(_enabled_policy()))
    for _ in range(settings.OTP_REQUEST_MAX_PER_WINDOW):
        await service.request_otp(AppOtpRequestCommand(email=TESTER))
    token_store.challenges.clear()

    with pytest.raises(TooManyRequestsException):
        await service.request_otp(AppOtpRequestCommand(email=TESTER))
    assert token_store.challenges == {}


@pytest.mark.asyncio
async def test_fixed_acknowledgement_does_not_reveal_whether_the_email_exists(stg):
    service, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()))

    unknown = await service.request_otp(AppOtpRequestCommand(email=TESTER))
    await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))
    known = await service.request_otp(AppOtpRequestCommand(email=TESTER))

    assert unknown == known


@pytest.mark.asyncio
@pytest.mark.parametrize("flaw", ["inactive", "unverified", "admin-only"])
async def test_fixed_code_does_not_bypass_credential_rejections(stg, flaw: str):
    service, user_repo, end_user_repo, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()))
    auth_user_id = uuid4()
    await user_repo.create_credential(auth_user_id=auth_user_id, email=TESTER, password_hash=None, is_admin=flaw == "admin-only", verified=flaw != "unverified")
    if flaw == "inactive":
        user_repo.by_email[TESTER] = user_repo.by_email[TESTER].model_copy(update={"is_active": False})
    if flaw != "admin-only":
        await end_user_repo.create_end_user(end_user_id=uuid4(), auth_user_id=auth_user_id)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))
    assert (auth_user_id in end_user_repo.by_auth_user_id) is (flaw != "admin-only")


_WITHDRAWN = {
    "disabled": OtpTestPolicy(project_id="rooted-app-dev", test_mode_enabled=False, allowlist=("*@test.example.com",)),
    "delisted": _enabled_policy("*@other.example.com"),
    "malformed-list": _enabled_policy("*@test.example.com", "*"),
    "wrong-project": _enabled_policy(project_id="rooted-app-prod"),
    "unusable": None,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawn", _WITHDRAWN.values(), ids=_WITHDRAWN.keys())
async def test_withdrawal_observed_at_verification_permanently_rejects_the_challenge(stg, withdrawn: Optional[OtpTestPolicy]):
    source = StubOtpTestPolicySource(_enabled_policy())
    service, *_rest = _build_service(source)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    source.policy = withdrawn
    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))

    source.policy = _enabled_policy()
    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))

    await service.request_otp(AppOtpRequestCommand(email=TESTER))
    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))).member.email == TESTER


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawn", _WITHDRAWN.values(), ids=_WITHDRAWN.keys())
async def test_withdrawal_observed_through_another_identity_is_not_revived_by_reenabling(stg, withdrawn: Optional[OtpTestPolicy]):
    source = StubOtpTestPolicySource(_enabled_policy())
    service, *_rest = _build_service(source)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    source.policy = withdrawn
    await service.request_otp(AppOtpRequestCommand(email="someone@elsewhere.example"))
    source.policy = _enabled_policy()

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))


@pytest.mark.asyncio
async def test_policy_changes_that_keep_an_identity_eligible_keep_its_challenge(stg):
    source = StubOtpTestPolicySource(_enabled_policy())
    service, *_rest = _build_service(source)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    source.policy = _enabled_policy("*@test.example.com", "new@example.com")

    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))).member.email == TESTER


@pytest.mark.asyncio
async def test_rotating_the_fixed_code_rejects_old_challenges_even_after_rotating_back(stg, monkeypatch: pytest.MonkeyPatch):
    service, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()))
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "654321")
    for code in ("123456", "654321"):
        with pytest.raises(UnauthorizedException):
            await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code=code))
    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "")
    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))

    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "654321")
    await service.request_otp(AppOtpRequestCommand(email=TESTER))
    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="654321"))).member.email == TESTER


@pytest.mark.asyncio
async def test_restart_with_a_rotated_code_withdraws_old_challenges_on_first_observation(stg, monkeypatch: pytest.MonkeyPatch):
    token_store = StubOtpTokenStore()
    before, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()), token_store)
    await before.request_otp(AppOtpRequestCommand(email=TESTER))

    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "654321")
    after, *_rest = _build_service(StubOtpTestPolicySource(_enabled_policy()), token_store)
    await after.request_otp(AppOtpRequestCommand(email="someone@elsewhere.example"))
    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "")

    with pytest.raises(UnauthorizedException):
        await after.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))


@pytest.mark.asyncio
async def test_emailed_challenge_survives_every_test_mode_change(stg, monkeypatch: pytest.MonkeyPatch):
    source = StubOtpTestPolicySource(None)
    service, *_rest, mailer, token_store = _build_service(source)
    # A random code may happen to equal the configured test passcode.
    monkeypatch.setattr("portal.application.auth.app_auth_service.secrets.randbelow", lambda _limit: 123456)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))
    assert mailer.sent[-1][1] == "123456"

    for policy in (_enabled_policy(), _WITHDRAWN["disabled"], None):
        source.policy = policy
        await service.request_otp(AppOtpRequestCommand(email=f"{uuid4().hex}@elsewhere.example"))
    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "654321")

    assert token_store.challenges[TESTER].delivery_mode is OtpDeliveryMode.EMAIL
    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))).member.email == TESTER


@pytest.mark.asyncio
async def test_emailed_challenge_is_not_redeemable_with_the_test_passcode_once_enabled(stg, monkeypatch: pytest.MonkeyPatch):
    source = StubOtpTestPolicySource(None)
    service, *_rest = _build_service(source)
    monkeypatch.setattr("portal.application.auth.app_auth_service.secrets.randbelow", lambda _limit: 42)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    source.policy = _enabled_policy()
    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))
    assert (await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="000042"))).member.email == TESTER


@pytest.mark.asyncio
async def test_fixed_mode_does_not_depend_on_the_mail_provider(stg):
    service, *_rest, mailer, _store = _build_service(StubOtpTestPolicySource(_enabled_policy()))
    mailer.fail = True

    result = await service.request_otp(AppOtpRequestCommand(email=TESTER))

    assert result.delivery_mode is OtpDeliveryMode.FIXED


@pytest.mark.asyncio
async def test_failed_delivery_only_drops_the_challenge_it_issued(stg, monkeypatch: pytest.MonkeyPatch):
    service, *_rest, mailer, token_store = _build_service()
    newer = OtpChallenge.of("jay@example.com", "777777", OtpDeliveryMode.EMAIL)

    async def superseded_then_fails(email: str, code: str, *, locale: Optional[str]) -> None:
        await token_store.store(email, newer, 600)
        raise OtpDeliveryError("provider down")

    monkeypatch.setattr(mailer, "send_otp", superseded_then_fails)
    with pytest.raises(ApiBaseException):
        await service.request_otp(AppOtpRequestCommand(email="jay@example.com"))

    assert token_store.challenges == {"jay@example.com": newer}


@pytest.mark.asyncio
async def test_unset_environment_is_not_treated_as_dev(stg, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr("portal.application.auth.otp_test_passcode_service.settings", Configuration())

    assert await _selected_mode(_enabled_policy(), TESTER) is OtpDeliveryMode.EMAIL


@pytest.mark.asyncio
async def test_withdrawal_observed_while_a_fixed_challenge_is_being_stored_cannot_be_revived(stg, monkeypatch: pytest.MonkeyPatch):
    source = StubOtpTestPolicySource(_enabled_policy())
    service, *_rest, mailer, token_store = _build_service(source)
    original_store = token_store.store

    async def store_after_withdrawal(email: str, challenge: OtpChallenge, ttl_seconds: int) -> None:
        if challenge.delivery_mode is OtpDeliveryMode.FIXED:
            source.policy = _WITHDRAWN["disabled"]
            await service.request_otp(AppOtpRequestCommand(email="someone@elsewhere.example"))
        await original_store(email, challenge, ttl_seconds)

    monkeypatch.setattr(token_store, "store", store_after_withdrawal)
    result = await service.request_otp(AppOtpRequestCommand(email=TESTER))
    source.policy = _enabled_policy()

    assert result.delivery_mode is OtpDeliveryMode.EMAIL
    assert mailer.sent[-1][0] == TESTER
    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))


@pytest.mark.asyncio
async def test_failed_withdrawal_is_completed_even_when_the_policy_is_reenabled_first(stg, monkeypatch: pytest.MonkeyPatch):
    enabled = _enabled_policy()
    source = StubOtpTestPolicySource(enabled)
    service, *_rest, token_store = _build_service(source)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))

    async def storage_down(*_args):
        raise ConnectionError("redis down")

    source.policy = _WITHDRAWN["disabled"]
    with monkeypatch.context() as outage:
        outage.setattr(token_store, "list_fixed", storage_down)
        with pytest.raises(ConnectionError):
            await service.request_otp(AppOtpRequestCommand(email="someone@elsewhere.example"))
    source.policy = enabled

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))


@pytest.mark.asyncio
async def test_withdrawal_is_observed_without_any_otp_traffic(stg):
    source = StubOtpTestPolicySource(_enabled_policy())
    token_store = StubOtpTokenStore()
    service, *_rest = _build_service(source, token_store)
    await service.request_otp(AppOtpRequestCommand(email=TESTER))
    watcher = asyncio.create_task(OtpTestPasscodeService(otp_test_policy=source, otp_token_store=token_store).watch(interval_seconds=0.001))

    source.policy = _WITHDRAWN["disabled"]
    await asyncio.sleep(0.02)
    source.policy = _enabled_policy()
    watcher.cancel()

    with pytest.raises(UnauthorizedException):
        await service.verify_otp(AppOtpVerifyCommand(email=TESTER, code="123456"))


@pytest.mark.asyncio
async def test_watching_survives_a_storage_outage(stg, monkeypatch: pytest.MonkeyPatch):
    source = StubOtpTestPolicySource(_enabled_policy())
    token_store = StubOtpTokenStore()
    original_list_fixed = token_store.list_fixed
    await token_store.store(TESTER, OtpChallenge.of(TESTER, "123456", OtpDeliveryMode.FIXED), 600)

    async def storage_down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(token_store, "list_fixed", storage_down)
    watcher = asyncio.create_task(OtpTestPasscodeService(otp_test_policy=source, otp_token_store=token_store).watch(interval_seconds=0.001))
    await asyncio.sleep(0.02)
    assert not watcher.done()
    monkeypatch.setattr(token_store, "list_fixed", original_list_fixed)
    await asyncio.sleep(0.02)
    watcher.cancel()

    assert token_store.challenges == {}


@pytest.mark.asyncio
async def test_production_never_watches_the_remote_policy(stg, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ENV", "prod")
    source = StubOtpTestPolicySource(_enabled_policy())

    await asyncio.wait_for(OtpTestPasscodeService(otp_test_policy=source, otp_token_store=StubOtpTokenStore()).watch(), timeout=1)

    assert source.reads == 0


def test_codes_and_allowlist_stay_out_of_object_representations():
    assert "482913" not in repr(AppOtpVerifyCommand(email=TESTER, code="482913"))
    assert "test.example.com" not in repr(_enabled_policy())
