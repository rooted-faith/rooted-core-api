"""
HTTP boundary for the App support policy lookup and the shared App build gate (ROO-163, ROO-171).

Requests go through the real public application: CORS, the gate, CoreRequestMiddleware,
AuthMiddleware, routing, and serialization. The policy lives in system settings (namespace
`app_support`); the settings table and Redis are in-memory fakes shared by the admin setting
API and the policy source, so an admin save can be followed by an App request in one test.
Feature services are stubs that record calls, so a rejected request can be checked for side effects.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from portal.application.app_support.app_support_service import AppSupportService
from portal.application.auth.results import AccessTokenPayload, OtpRequestResult, UserDetail, UserSensitive
from portal.application.devotion.results import EncounterResult
from portal.application.system.setting_service import SettingService
from portal.apps import get_public_application
from portal.container import Container
from portal.domain.app_support.constants import APP_SUPPORT_SETTING_NAMESPACE, AppSupportEnforcement
from portal.domain.bible.entities import BibleVerse
from portal.domain.devotion.entities import AnonymousDailyLesson, Passage
from portal.domain.system.entities import Setting
from portal.infrastructure.app_support.setting_policy_source import LAST_KNOWN_GOOD_MAX_AGE_SECONDS, SettingAppSupportPolicySource

POLICY_URL = "/api/v1/app-support/policy"
TODAY_URL = "/api/v1/devotion/today?date=2026-11-28"
OTP_URL = "/api/v1/auth/otp"
SETTINGS_URL = "/admin/api/v1/system/settings"

IOS_POLICY: dict[str, Any] = {"minimum_build": 20, "latest_build": 25, "update_url": "https://testflight.apple.com/join/abc123"}
ANDROID_POLICY: dict[str, Any] = {"minimum_build": 7, "update_instructions": "Install the newest staging APK from the team drive."}
POLICY: dict[str, Any] = {"ios": IOS_POLICY, "android": ANDROID_POLICY}


class _RecordingDb:
    def __init__(self) -> None:
        self.opened = 0
        self.committed = 0

    def __call__(self) -> "_RecordingDb":
        self.opened += 1
        return self

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _SettingTable:
    """In-memory system_setting rows with the SettingRepository surface the admin service uses."""

    def __init__(self) -> None:
        self.rows: dict[UUID, Setting] = {}

    def put(self, setting_key: str, value: Any, *, namespace: str = APP_SUPPORT_SETTING_NAMESPACE, value_type: str = "object", is_active: bool = True) -> UUID:
        """Store a row directly, bypassing admin validation (a value saved before validation existed, or by SQL)."""
        setting_id = uuid4()
        self.rows[setting_id] = Setting(
            id=setting_id,
            namespace=namespace,
            setting_key=setting_key,
            value_type=value_type,
            value=value,
            is_active=is_active,
            created_at=datetime.now(timezone.utc),
        )
        return setting_id

    def value(self, setting_key: str) -> Any:
        row = self._find(APP_SUPPORT_SETTING_NAMESPACE, setting_key, include_deleted=False)
        return row.value if row else None

    def _find(self, namespace: str, setting_key: str, *, include_deleted: bool) -> Setting | None:
        for row in self.rows.values():
            if row.namespace == namespace and row.setting_key == setting_key and (include_deleted or not row.is_deleted):
                return row
        return None

    async def get_by_id(self, setting_id: UUID, *, include_deleted: bool = False) -> Setting | None:
        row = self.rows.get(setting_id)
        if row is None or (row.is_deleted and not include_deleted):
            return None
        return row

    async def get_by_namespace_key(self, namespace: str, setting_key: str, *, include_deleted: bool = False) -> Setting | None:
        return self._find(namespace, setting_key, include_deleted=include_deleted)

    async def insert(self, payload: dict[str, Any]) -> None:
        self.rows[payload["id"]] = Setting(**payload, created_at=datetime.now(timezone.utc))

    async def update_value(self, setting_id: UUID, value: Any, remark: str | None = None) -> int:
        row = await self.get_by_id(setting_id)
        if row is None:
            return 0
        self.rows[setting_id] = row.model_copy(update={"value": value, "remark": remark if remark is not None else row.remark})
        return 1

    async def delete_soft(self, setting_id: UUID, reason: str | None) -> int:
        row = await self.get_by_id(setting_id)
        if row is None:
            return 0
        self.rows[setting_id] = row.model_copy(update={"is_deleted": True, "delete_reason": reason})
        return 1


class _DatabaseReader:
    """The policy source's own database read (it runs outside the request session)."""

    def __init__(self, table: _SettingTable) -> None:
        self._table = table
        self.reads = 0
        self.down = False
        self.hangs = False

    async def __call__(self, namespace: str, setting_key: str) -> Setting | None:
        if self.down:
            raise ConnectionRefusedError("database is unavailable")
        if self.hangs:
            await asyncio.sleep(60)
        self.reads += 1
        return await self._table.get_by_namespace_key(namespace, setting_key)


class _FakeSettingCache:
    """Shared Redis stand-in for the admin setting service and the policy source."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], Any] = {}
        self.ttls: dict[tuple[str, str], int] = {}
        self.reads = 0
        self.down = False
        self.hangs = False

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError("redis is unavailable")

    async def lookup(self, namespace: str, setting_key: str) -> tuple[bool, Any]:
        self._check()
        if self.hangs:
            await asyncio.sleep(60)
        self.reads += 1
        key = (namespace, setting_key)
        return (key in self.values, self.values.get(key))

    async def set_value(self, namespace: str, setting_key: str, value: Any, ex: int | None = None) -> None:
        self._check()
        self.values[(namespace, setting_key)] = value
        self.ttls[(namespace, setting_key)] = ex

    async def invalidate(self, namespace: str, setting_key: str) -> None:
        self._check()
        self.values.pop((namespace, setting_key), None)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class _StubLocaleService:
    async def get_locale_snapshot(self) -> dict:
        return {"active_locales": ["en"], "default_locale": "en", "normalized_map": {"en": "en"}, "normalized_id_map": {}}

    async def get_locale_codes_by_language(self, language_code: str) -> list[str]:
        return []


class _RecordingDevotionService:
    def __init__(self) -> None:
        self.calls: list[date] = []

    async def get_daily_lesson(self, lesson_date, locale_id, locale_code, include_authored_sections, auth_user_id=None):
        self.calls.append(lesson_date)
        verse = BibleVerse(passage_id="JHN.3.16", verse=16, lines=[])
        return AnonymousDailyLesson(date=lesson_date, passage=Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=[verse]))

    async def record_encounter(self, *, auth_user_id, encounter_date, time_zone):
        self.calls.append(encounter_date)
        return EncounterResult(date=encounter_date, current_streak=1, longest_streak=1, welcome_back=False)


VALID_TOKEN = "valid.member.token"
MEMBER_ID = UUID("019dd0c8-0000-7000-8000-000000000001")
ADMIN_TOKEN = "valid.admin.token"
ADMIN_ID = UUID("019dd0c8-0000-7000-8000-0000000000ad")
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


class _StubJwtProvider:
    def verify_token(self, token: str, is_admin: bool = False):
        if is_admin:
            if token != ADMIN_TOKEN:
                return None
            return AccessTokenPayload(
                sub=ADMIN_ID, user_id=ADMIN_ID, exp=4102444800, aud="admin", iat=0, iss="test", email="ops@example.com", family_id=uuid4()
            )
        if token != VALID_TOKEN:
            return None
        return AccessTokenPayload(
            sub=MEMBER_ID, user_id=MEMBER_ID, exp=4102444800, aud="user", iat=0, iss="test", email="reader@example.com", family_id=uuid4(), azp="rooted-app"
        )


class _StubUserReadService:
    async def get_user_detail_by_id(self, user_id):
        return UserDetail(id=user_id, email="reader@example.com", verified=True, is_active=True)

    async def get_user_sensitive_by_id(self, user_id):
        return UserSensitive(id=user_id, email="ops@example.com", verified=True, is_active=True, is_admin=True)


class _StubPermissionChecker:
    def __init__(self) -> None:
        self.granted: set[str] = set()

    async def has_any_permission(self, permission_codes: list[str], user_id=None) -> bool:
        return any(code in self.granted for code in permission_codes)

    async def has_all_permissions(self, permission_codes: list[str], user_id=None) -> bool:
        return all(code in self.granted for code in permission_codes)


class _RecordingAuthService:
    def __init__(self) -> None:
        self.emails: list[str] = []

    async def request_otp(self, command):
        self.emails.append(command.email)
        return OtpRequestResult(message="ok", delivery_mode="email")


class Harness:
    def __init__(self, *, policy: dict[str, Any] | None, environment: str, enforcement: AppSupportEnforcement) -> None:
        self.db = _RecordingDb()
        self.devotion = _RecordingDevotionService()
        self.auth = _RecordingAuthService()
        self.settings = _SettingTable()
        self.cache = _FakeSettingCache()
        self.database = _DatabaseReader(self.settings)
        self.clock = _Clock()
        self.permissions = _StubPermissionChecker()
        self.setting_ids: dict[str, UUID] = {}
        for platform, value in (policy or {}).items():
            self.setting_ids[platform] = self.settings.put(platform, value)

        source = SettingAppSupportPolicySource(
            environment=environment, setting_cache=self.cache, load_setting=self.database, clock=self.clock, cache_timeout=0.05, database_timeout=0.05
        )
        service = AppSupportService(policy_source=source, enforcement=enforcement)

        container = Container()
        container.db_session.override(providers.Callable(self.db))
        container.locale_service.override(providers.Object(_StubLocaleService()))
        container.devotion_service.override(providers.Object(self.devotion))
        container.app_auth_service.override(providers.Object(self.auth))
        container.app_support_service.override(providers.Object(service))
        container.setting_service.override(providers.Object(SettingService(setting_repository=self.settings, setting_cache=self.cache)))
        container.permission_checker.override(providers.Object(self.permissions))
        container.jwt_provider.override(providers.Object(_StubJwtProvider()))
        container.user_read_service.override(providers.Object(_StubUserReadService()))
        self.client = AsyncClient(transport=ASGITransport(app=get_public_application(container)), base_url="http://testserver")

    @property
    def feature_calls(self) -> int:
        return len(self.devotion.calls) + len(self.auth.emails)

    def grant(self, *codes: str) -> None:
        self.permissions.granted.update(codes)

    async def healthz_session_opens(self) -> int:
        """Database sessions a /healthz request opens: the public app's own stack, outside the App API."""
        before = self.db.opened
        await self.client.get("/healthz")
        opened = self.db.opened - before
        self.db.opened = 0
        return opened


@pytest.fixture
def make_harness():
    def _make(*, policy: dict[str, Any] | None = POLICY, environment: str = "stg", enforcement: str = "compatible") -> Harness:
        return Harness(policy=policy, environment=environment, enforcement=AppSupportEnforcement(enforcement))

    return _make


def ios(build: int | str) -> dict[str, str]:
    return {"X-App-Platform": "ios", "X-App-Build": str(build)}


def android(build: int | str) -> dict[str, str]:
    return {"X-App-Platform": "android", "X-App-Build": str(build)}


# --- Policy lookup -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_lookup_needs_no_sign_in_and_returns_the_server_environment_policy(make_harness):
    harness = make_harness()

    response = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "environment": "stg",
        "platform": "ios",
        "minimumBuild": 20,
        "latestBuild": 25,
        "updateUrl": "https://testflight.apple.com/join/abc123",
        "updateInstructions": None,
        "enforcement": "compatible",
    }


@pytest.mark.asyncio
async def test_policy_lookup_keeps_ios_and_android_separate(make_harness):
    harness = make_harness()

    response = await harness.client.get(POLICY_URL, params={"platform": "android"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "android"
    assert body["minimumBuild"] == 7
    assert body["latestBuild"] is None
    assert body["updateUrl"] is None
    assert body["updateInstructions"] == "Install the newest staging APK from the team drive."


@pytest.mark.asyncio
async def test_policy_lookup_reports_the_server_environment_and_ignores_client_hints(make_harness):
    harness = make_harness(environment="prod")

    response = await harness.client.get(POLICY_URL, params={"platform": "ios", "environment": "stg"}, headers={"X-App-Environment": "stg"})

    assert response.status_code == 200
    assert response.json()["environment"] == "prod"
    assert response.json()["minimumBuild"] == 20


@pytest.mark.asyncio
async def test_policy_lookup_is_never_gated_even_when_enforced(make_harness):
    harness = make_harness(enforcement="enforced")

    old_app = await harness.client.get(POLICY_URL, params={"platform": "ios"}, headers=ios(1))
    legacy_app = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert old_app.status_code == 200
    assert legacy_app.status_code == 200
    assert legacy_app.json()["enforcement"] == "enforced"


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", [None, "", "web", "windows"])
async def test_policy_lookup_rejects_an_unknown_platform(make_harness, platform):
    harness = make_harness()

    params = {} if platform is None else {"platform": platform}
    response = await harness.client.get(POLICY_URL, params=params)

    assert response.status_code == 400
    assert response.json()["error_code"] == "APP_IDENTITY_INVALID"


@pytest.mark.asyncio
async def test_policy_lookup_reports_unavailable_when_no_setting_exists(make_harness):
    harness = make_harness(policy=None)

    response = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"
    assert response.json()["context"] == {"platform": "ios"}


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [None, "not an object", ["ios"], 42])
async def test_policy_lookup_reports_unavailable_for_a_stored_value_that_is_not_a_policy_object(make_harness, stored):
    harness = make_harness(policy={"ios": stored, "android": ANDROID_POLICY})

    ios_response = await harness.client.get(POLICY_URL, params={"platform": "ios"})
    android_response = await harness.client.get(POLICY_URL, params={"platform": "android"})

    assert ios_response.status_code == 503
    assert ios_response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"
    assert android_response.status_code == 200


@pytest.mark.asyncio
async def test_an_inactive_setting_is_unavailable(make_harness):
    harness = make_harness(policy={"android": ANDROID_POLICY})
    harness.settings.put("ios", IOS_POLICY, is_active=False)

    response = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ios_policy",
    [
        {"minimum_build": -1, "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": "20", "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": 2.5, "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": True, "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": 20, "latest_build": 19, "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": 20},
        {"minimum_build": 20, "update_instructions": "   "},
        {"minimum_build": 20, "update_url": "http://testflight.apple.com/join/abc"},
        {"minimum_build": 20, "update_url": "javascript:alert(1)"},
        {"minimum_build": 20, "update_url": "https:///join"},
        {"minimum_build": 20, "update_url": "https://testflight.apple.com/join/abc", "minimum": 30},
    ],
)
async def test_an_invalid_stored_policy_is_unavailable_without_affecting_the_other_platform(make_harness, ios_policy):
    harness = make_harness(policy={"ios": ios_policy, "android": ANDROID_POLICY})

    ios_response = await harness.client.get(POLICY_URL, params={"platform": "ios"})
    android_response = await harness.client.get(POLICY_URL, params={"platform": "android"})

    assert ios_response.status_code == 503
    assert ios_response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"
    assert android_response.status_code == 200
    assert android_response.json()["minimumBuild"] == 7


# --- Gate: compatible introduction mode ----------------------------------------------------------


@pytest.mark.asyncio
async def test_compatible_mode_lets_legacy_and_unsupported_apps_through(make_harness):
    harness = make_harness(enforcement="compatible")

    legacy = await harness.client.get(TODAY_URL)
    below_minimum = await harness.client.get(TODAY_URL, headers=ios(1))
    malformed = await harness.client.get(TODAY_URL, headers={"X-App-Platform": "web", "X-App-Build": "abc"})

    assert [legacy.status_code, below_minimum.status_code, malformed.status_code] == [200, 200, 200]
    assert len(harness.devotion.calls) == 3


@pytest.mark.asyncio
async def test_compatible_mode_ignores_a_missing_policy(make_harness):
    harness = make_harness(policy=None, enforcement="compatible")

    response = await harness.client.get(TODAY_URL, headers=ios(1))

    assert response.status_code == 200


# --- Gate: enforced mode -------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("build", [20, 21, 25, 26, 999])
async def test_enforced_gate_admits_builds_at_or_above_minimum_including_newer_than_latest(make_harness, build):
    harness = make_harness(enforcement="enforced")

    response = await harness.client.get(TODAY_URL, headers=ios(build))

    assert response.status_code == 200
    assert response.json()["date"] == "2026-11-28"
    assert len(harness.devotion.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("build", [0, 1, 19])
async def test_enforced_gate_requires_an_update_below_minimum_before_any_side_effect(make_harness, build):
    harness = make_harness(enforcement="enforced")
    baseline = await harness.healthz_session_opens()

    response = await harness.client.get(TODAY_URL, headers=ios(build))

    assert response.status_code == 426
    assert response.json()["error_code"] == "APP_UPDATE_REQUIRED"
    assert response.json()["context"] == {"platform": "ios", "build": build, "minimum_build": 20}
    assert harness.feature_calls == 0
    assert harness.db.opened == baseline


@pytest.mark.asyncio
async def test_enforced_gate_applies_each_platform_its_own_minimum(make_harness):
    harness = make_harness(enforcement="enforced")

    android_7 = await harness.client.get(TODAY_URL, headers=android(7))
    ios_7 = await harness.client.get(TODAY_URL, headers=ios(7))
    android_6 = await harness.client.get(TODAY_URL, headers=android(6))

    assert android_7.status_code == 200
    assert ios_7.status_code == 426
    assert android_6.status_code == 426
    assert android_6.json()["context"]["minimum_build"] == 7


@pytest.mark.asyncio
async def test_enforced_gate_ignores_a_client_environment_hint(make_harness):
    harness = make_harness(environment="prod", enforcement="enforced")

    response = await harness.client.get(TODAY_URL, headers={**ios(19), "X-App-Environment": "dev"})

    assert response.status_code == 426
    assert response.json()["context"]["minimum_build"] == 20


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-App-Platform": "ios"},
        {"X-App-Build": "20"},
        {"X-App-Platform": "web", "X-App-Build": "20"},
        {"X-App-Platform": "", "X-App-Build": "20"},
        {"X-App-Platform": "ios", "X-App-Build": ""},
        {"X-App-Platform": "ios", "X-App-Build": "-1"},
        {"X-App-Platform": "ios", "X-App-Build": "20.1"},
        {"X-App-Platform": "ios", "X-App-Build": "1.2.3"},
        {"X-App-Platform": "ios", "X-App-Build": "abc"},
        {"X-App-Platform": "ios", "X-App-Build": "+20"},
        {"X-App-Platform": "ios", "X-App-Build": "1" * 10},
        {"X-App-Platform": "ios", "X-App-Build": "２０".encode()},
    ],
)
async def test_enforced_gate_rejects_missing_or_malformed_identity_before_any_side_effect(make_harness, headers):
    harness = make_harness(enforcement="enforced")
    baseline = await harness.healthz_session_opens()

    response = await harness.client.get(TODAY_URL, headers=headers)

    assert response.status_code == 400
    assert response.json()["error_code"] == "APP_IDENTITY_INVALID"
    assert harness.feature_calls == 0
    assert harness.db.opened == baseline


@pytest.mark.asyncio
async def test_enforced_gate_accepts_identity_case_and_whitespace_variants(make_harness):
    harness = make_harness(enforcement="enforced")

    response = await harness.client.get(TODAY_URL, headers={"X-App-Platform": " iOS ", "X-App-Build": " 20 "})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_enforced_gate_reports_policy_unavailable_distinctly(make_harness):
    harness = make_harness(policy={"android": ANDROID_POLICY}, enforcement="enforced")

    ios_response = await harness.client.get(TODAY_URL, headers=ios(500))
    android_response = await harness.client.get(TODAY_URL, headers=android(7))

    assert ios_response.status_code == 503
    assert ios_response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"
    assert android_response.status_code == 200
    assert len(harness.devotion.calls) == 1


@pytest.mark.asyncio
async def test_enforced_gate_covers_app_auth_routes(make_harness):
    harness = make_harness(enforcement="enforced")

    rejected = await harness.client.post(OTP_URL, json={"email": "reader@example.com"}, headers=ios(3))
    admitted = await harness.client.post(OTP_URL, json={"email": "reader@example.com"}, headers=ios(20))

    assert rejected.status_code == 426
    assert admitted.status_code == 200
    assert harness.auth.emails == ["reader@example.com"]


@pytest.mark.asyncio
async def test_update_required_wins_over_an_expired_sign_in(make_harness):
    harness = make_harness(enforcement="enforced")

    response = await harness.client.get(TODAY_URL, headers={**ios(3), "Authorization": "Bearer expired.token.value"})

    assert response.status_code == 426
    assert response.json()["error_code"] == "APP_UPDATE_REQUIRED"


@pytest.mark.asyncio
async def test_a_supported_app_still_goes_through_normal_auth(make_harness):
    harness = make_harness(enforcement="enforced")

    response = await harness.client.post("/api/v1/devotion/encounters", json={"date": "2026-11-28"}, headers=ios(20))

    assert response.status_code == 401
    assert "error_code" not in response.json() or not response.json()["error_code"].startswith("APP_")


@pytest.mark.asyncio
async def test_a_supported_signed_in_app_reaches_the_feature_and_an_unsupported_one_does_not(make_harness):
    harness = make_harness(enforcement="enforced")
    signed_in = {"Authorization": f"Bearer {VALID_TOKEN}"}

    rejected = await harness.client.post("/api/v1/devotion/encounters", json={"date": "2026-11-28"}, headers={**signed_in, **ios(19)})
    admitted = await harness.client.post("/api/v1/devotion/encounters", json={"date": "2026-11-28"}, headers={**signed_in, **ios(20)})

    assert rejected.status_code == 426
    assert admitted.status_code == 200
    assert admitted.json()["currentStreak"] == 1
    assert harness.devotion.calls == [date(2026, 11, 28)]


@pytest.mark.asyncio
async def test_rejections_keep_cors_headers_for_browser_clients(make_harness):
    harness = make_harness(enforcement="enforced")

    response = await harness.client.get(TODAY_URL, headers={**ios(1), "Origin": "http://localhost:5174"})

    assert response.status_code == 426
    assert "access-control-allow-origin" in response.headers


# --- Exempt surfaces -----------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "/healthz"),
        ("POST", "/admin/api/v1/auth/login"),
        ("GET", "/admin/api/v1/users"),
        ("POST", "/webhooks/resend/email-events"),
        ("GET", "/api/openapi.json"),
        ("GET", "/api/docs"),
    ],
)
async def test_exempt_surfaces_are_never_gated(make_harness, method, url):
    harness = make_harness(enforcement="enforced")

    response = await harness.client.request(method, url, headers={"X-App-Platform": "ios", "X-App-Build": "0"})
    unidentified = await harness.client.request(method, url)

    # The surface may fail for its own reasons (an unconfigured webhook answers 503); it must not be the gate.
    for result in (response, unidentified):
        assert result.status_code != 426
        error_code = result.json().get("error_code", "") if result.headers.get("content-type", "").startswith("application/json") else ""
        assert not str(error_code).startswith("APP_")


# --- Policy in system settings: admin writes apply without a restart (ROO-171) --------------------


@pytest.mark.asyncio
async def test_an_admin_save_applies_to_lookup_and_gate_on_the_next_request(make_harness):
    harness = make_harness(enforcement="enforced")
    harness.grant("system:setting:read", "system:setting:update")
    assert (await harness.client.get(TODAY_URL, headers=ios(20))).status_code == 200

    saved = await harness.client.put(
        f"{SETTINGS_URL}/{harness.setting_ids['ios']}", json={"value": {**IOS_POLICY, "minimum_build": 30, "latest_build": 30}}, headers=ADMIN
    )
    lookup = await harness.client.get(POLICY_URL, params={"platform": "ios"})
    gated = await harness.client.get(TODAY_URL, headers=ios(20))
    android_still = await harness.client.get(TODAY_URL, headers=android(7))

    assert saved.status_code == 200
    assert lookup.json()["minimumBuild"] == 30
    assert gated.status_code == 426
    assert gated.json()["context"]["minimum_build"] == 30
    assert android_still.status_code == 200


@pytest.mark.asyncio
async def test_an_admin_created_policy_makes_an_unavailable_platform_available(make_harness):
    harness = make_harness(policy={"android": ANDROID_POLICY}, enforcement="enforced")
    harness.grant("system:setting:create")
    assert (await harness.client.get(TODAY_URL, headers=ios(20))).status_code == 503

    created = await harness.client.post(
        SETTINGS_URL, json={"namespace": "app_support", "setting_key": "ios", "value_type": "object", "value": IOS_POLICY}, headers=ADMIN
    )
    admitted = await harness.client.get(TODAY_URL, headers=ios(20))

    assert created.status_code == 201
    assert admitted.status_code == 200


@pytest.mark.asyncio
async def test_deleting_a_policy_setting_makes_only_that_platform_unavailable(make_harness):
    harness = make_harness(enforcement="enforced")
    harness.grant("system:setting:delete")
    assert (await harness.client.get(TODAY_URL, headers=ios(20))).status_code == 200

    deleted = await harness.client.request("DELETE", f"{SETTINGS_URL}/{harness.setting_ids['ios']}", json={"reason": "test"}, headers=ADMIN)
    ios_response = await harness.client.get(TODAY_URL, headers=ios(20))
    android_response = await harness.client.get(TODAY_URL, headers=android(7))

    assert deleted.status_code == 204
    assert ios_response.status_code == 503
    assert ios_response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"
    assert android_response.status_code == 200


@pytest.mark.asyncio
async def test_saving_a_policy_needs_the_system_setting_permission(make_harness):
    harness = make_harness()
    harness.grant("system:setting:read")

    response = await harness.client.put(f"{SETTINGS_URL}/{harness.setting_ids['ios']}", json={"value": {**IOS_POLICY, "minimum_build": 99}}, headers=ADMIN)

    assert response.status_code == 403
    assert harness.settings.value("ios") == IOS_POLICY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        {"minimum_build": -1, "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": "30", "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": 30, "latest_build": 29, "update_url": "https://testflight.apple.com/join/abc"},
        {"minimum_build": 30},
        {"minimum_build": 30, "update_url": "http://testflight.apple.com/join/abc"},
        {"minimum_build": 30, "update_url": "https://testflight.apple.com/join/abc", "minimun_build": 31},
    ],
)
async def test_an_invalid_policy_update_is_rejected_and_the_saved_policy_stays_in_force(make_harness, value):
    harness = make_harness(enforcement="enforced")
    harness.grant("system:setting:update")

    response = await harness.client.put(f"{SETTINGS_URL}/{harness.setting_ids['ios']}", json={"value": value}, headers=ADMIN)

    assert response.status_code == 400
    assert response.json()["error_code"] == "SYSTEM_SETTING_VALUE_INVALID"
    assert response.json()["context"]["reasons"]
    assert harness.settings.value("ios") == IOS_POLICY
    assert (await harness.client.get(TODAY_URL, headers=ios(20))).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setting_key", "value_type", "value"),
    [
        ("ios", "object", {"minimum_build": 30}),
        ("ios", "string", '{"minimum_build": 30, "update_url": "https://testflight.apple.com/join/abc"}'),
        ("web", "object", IOS_POLICY),
        ("IOS", "object", IOS_POLICY),
    ],
)
async def test_an_invalid_policy_create_is_rejected(make_harness, setting_key, value_type, value):
    harness = make_harness(policy=None)
    harness.grant("system:setting:create")

    response = await harness.client.post(
        SETTINGS_URL, json={"namespace": "app_support", "setting_key": setting_key, "value_type": value_type, "value": value}, headers=ADMIN
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "SYSTEM_SETTING_VALUE_INVALID"
    assert harness.settings.rows == {}


@pytest.mark.asyncio
async def test_settings_outside_the_app_support_namespace_keep_their_generic_rules(make_harness):
    harness = make_harness(policy=None)
    harness.grant("system:setting:create")

    response = await harness.client.post(
        SETTINGS_URL, json={"namespace": "feature", "setting_key": "ios", "value_type": "object", "value": {"anything": True}}, headers=ADMIN
    )

    assert response.status_code == 201


# --- Per-request cost ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_gate_reads_redis_per_request_and_the_database_only_on_a_cache_miss(make_harness):
    harness = make_harness(enforcement="enforced")

    for _ in range(5):
        assert (await harness.client.get(TODAY_URL, headers=ios(20))).status_code == 200

    assert harness.cache.reads == 5
    assert harness.database.reads == 1
    assert harness.cache.ttls[("app_support", "ios")] == 60


@pytest.mark.asyncio
async def test_compatible_mode_reads_no_policy_on_gated_requests(make_harness):
    harness = make_harness(enforcement="compatible")

    await harness.client.get(TODAY_URL, headers=ios(1))

    assert harness.cache.reads == 0
    assert harness.database.reads == 0


@pytest.mark.asyncio
async def test_a_missing_policy_is_not_cached(make_harness):
    harness = make_harness(policy=None, enforcement="enforced")

    await harness.client.get(TODAY_URL, headers=ios(20))
    await harness.client.get(TODAY_URL, headers=ios(20))

    assert harness.database.reads == 2
    assert harness.cache.values == {}


# --- Redis or database outage --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_redis_outage_falls_back_to_the_database_and_still_enforces(make_harness):
    harness = make_harness(enforcement="enforced")
    harness.cache.down = True

    rejected = await harness.client.get(TODAY_URL, headers=ios(19))
    admitted = await harness.client.get(TODAY_URL, headers=ios(20))
    lookup = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert rejected.status_code == 426
    assert admitted.status_code == 200
    assert lookup.json()["minimumBuild"] == 20
    assert harness.database.reads == 3


@pytest.mark.asyncio
async def test_a_redis_and_database_outage_uses_the_last_known_good_policy_for_a_short_time(make_harness):
    harness = make_harness(enforcement="enforced")
    assert (await harness.client.get(TODAY_URL, headers=ios(20))).status_code == 200
    harness.cache.down = True
    harness.database.down = True

    harness.clock.now += LAST_KNOWN_GOOD_MAX_AGE_SECONDS
    rejected = await harness.client.get(TODAY_URL, headers=ios(19))
    admitted = await harness.client.get(TODAY_URL, headers=ios(20))
    harness.clock.now += 1
    expired = await harness.client.get(TODAY_URL, headers=ios(20))

    assert rejected.status_code == 426
    assert admitted.status_code == 200
    assert expired.status_code == 503
    assert expired.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_an_outage_with_no_last_known_good_policy_fails_closed_per_platform(make_harness):
    harness = make_harness(enforcement="enforced")
    assert (await harness.client.get(TODAY_URL, headers=android(7))).status_code == 200
    harness.cache.down = True
    harness.database.down = True

    ios_response = await harness.client.get(TODAY_URL, headers=ios(500))
    android_response = await harness.client.get(TODAY_URL, headers=android(7))
    lookup = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert ios_response.status_code == 503
    assert ios_response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"
    assert android_response.status_code == 200
    assert lookup.status_code == 503
    assert harness.devotion.calls == [date(2026, 11, 28), date(2026, 11, 28)]


@pytest.mark.asyncio
async def test_a_database_outage_on_a_cache_miss_never_admits_an_unsupported_build(make_harness):
    harness = make_harness(enforcement="enforced")
    harness.database.down = True

    response = await harness.client.get(TODAY_URL, headers=ios(1))

    assert response.status_code == 503
    assert harness.feature_calls == 0


@pytest.mark.asyncio
async def test_the_last_known_good_copy_follows_the_newest_successful_read(make_harness):
    harness = make_harness(enforcement="enforced")
    harness.grant("system:setting:update")
    await harness.client.get(TODAY_URL, headers=ios(20))
    await harness.client.put(f"{SETTINGS_URL}/{harness.setting_ids['ios']}", json={"value": {**IOS_POLICY, "minimum_build": 25}}, headers=ADMIN)
    await harness.client.get(TODAY_URL, headers=ios(25))
    harness.cache.down = True
    harness.database.down = True

    response = await harness.client.get(TODAY_URL, headers=ios(24))

    assert response.status_code == 426
    assert response.json()["context"]["minimum_build"] == 25


@pytest.mark.asyncio
async def test_a_hung_redis_or_database_times_out_instead_of_hanging_the_gate(make_harness):
    harness = make_harness(enforcement="enforced")
    harness.cache.hangs = True

    via_database = await asyncio.wait_for(harness.client.get(TODAY_URL, headers=ios(19)), timeout=5)
    harness.database.hangs = True
    from_last_known_good = await asyncio.wait_for(harness.client.get(TODAY_URL, headers=ios(19)), timeout=5)
    cold_platform = await asyncio.wait_for(harness.client.get(TODAY_URL, headers=android(7)), timeout=5)

    assert via_database.status_code == 426
    assert from_last_known_good.status_code == 426
    assert cold_platform.status_code == 503
