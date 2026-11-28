"""
HTTP boundary for the App support policy lookup and the shared App build gate (ROO-163).

Requests go through the real public application: CORS, the gate, CoreRequestMiddleware,
AuthMiddleware, routing, and serialization. Feature services are stubs that record calls,
so a rejected request can be checked for side effects.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from portal.application.app_support.app_support_service import AppSupportService
from portal.application.auth.results import AccessTokenPayload, OtpRequestResult, UserDetail
from portal.application.devotion.results import EncounterResult
from portal.apps import get_public_application
from portal.container import Container
from portal.domain.app_support.constants import AppSupportEnforcement
from portal.domain.bible.entities import BibleVerse
from portal.domain.devotion.entities import AnonymousDailyLesson, Passage
from portal.infrastructure.app_support.env_policy_source import EnvAppSupportPolicySource

POLICY_URL = "/api/v1/app-support/policy"
TODAY_URL = "/api/v1/devotion/today?date=2026-11-28"
OTP_URL = "/api/v1/auth/otp"

POLICY: dict[str, Any] = {
    "stg": {
        "ios": {"minimum_build": 20, "latest_build": 25, "update_url": "https://testflight.apple.com/join/abc123"},
        "android": {"minimum_build": 7, "update_instructions": "Install the newest staging APK from the team drive."},
    },
    "prod": {
        "ios": {"minimum_build": 90, "update_url": "https://apps.apple.com/app/id000000001"},
        "android": {"minimum_build": 80, "update_url": "https://play.google.com/store/apps/details?id=app.rootedfaith"},
    },
}


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


class _StubJwtProvider:
    def verify_token(self, token: str, is_admin: bool = False):
        if token != VALID_TOKEN:
            return None
        return AccessTokenPayload(
            sub=MEMBER_ID, user_id=MEMBER_ID, exp=4102444800, aud="user", iat=0, iss="test", email="reader@example.com", family_id=uuid4(), azp="rooted-app"
        )


class _StubUserReadService:
    async def get_user_detail_by_id(self, user_id):
        return UserDetail(id=user_id, email="reader@example.com", verified=True, is_active=True)


class _RecordingAuthService:
    def __init__(self) -> None:
        self.emails: list[str] = []

    async def request_otp(self, command):
        self.emails.append(command.email)
        return OtpRequestResult(message="ok", delivery_mode="email")


class Harness:
    def __init__(self, *, policy: Any, environment: str, enforcement: AppSupportEnforcement) -> None:
        self.db = _RecordingDb()
        self.devotion = _RecordingDevotionService()
        self.auth = _RecordingAuthService()
        raw = policy if policy is None or isinstance(policy, str) else json.dumps(policy)
        service = AppSupportService(policy_source=EnvAppSupportPolicySource(raw=raw, environment=environment), enforcement=enforcement)

        container = Container()
        container.db_session.override(providers.Callable(self.db))
        container.locale_service.override(providers.Object(_StubLocaleService()))
        container.devotion_service.override(providers.Object(self.devotion))
        container.app_auth_service.override(providers.Object(self.auth))
        container.app_support_service.override(providers.Object(service))
        container.jwt_provider.override(providers.Object(_StubJwtProvider()))
        container.user_read_service.override(providers.Object(_StubUserReadService()))
        self.client = AsyncClient(transport=ASGITransport(app=get_public_application(container)), base_url="http://testserver")

    @property
    def feature_calls(self) -> int:
        return len(self.devotion.calls) + len(self.auth.emails)

    async def healthz_session_opens(self) -> int:
        """Database sessions a /healthz request opens: the public app's own stack, outside the App API."""
        before = self.db.opened
        await self.client.get("/healthz")
        opened = self.db.opened - before
        self.db.opened = 0
        return opened


@pytest.fixture
def make_harness():
    def _make(*, policy: Any = POLICY, environment: str = "stg", enforcement: str = "compatible") -> Harness:
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
async def test_policy_lookup_uses_only_the_server_environment(make_harness):
    harness = make_harness(environment="prod")

    response = await harness.client.get(POLICY_URL, params={"platform": "ios", "environment": "stg"}, headers={"X-App-Environment": "stg"})

    assert response.status_code == 200
    assert response.json()["environment"] == "prod"
    assert response.json()["minimumBuild"] == 90


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
async def test_policy_lookup_reports_unavailable_when_the_environment_has_no_policy(make_harness):
    harness = make_harness(environment="dev")

    response = await harness.client.get(POLICY_URL, params={"platform": "ios"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "APP_SUPPORT_POLICY_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [None, "", "not json", "[]", json.dumps({"stg": "ios"})])
async def test_policy_lookup_reports_unavailable_for_missing_or_malformed_configuration(make_harness, raw):
    harness = make_harness(policy=raw)

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
async def test_an_invalid_platform_policy_is_unavailable_without_affecting_the_other_platform(make_harness, ios_policy):
    policy = {"stg": {"ios": ios_policy, "android": POLICY["stg"]["android"]}}
    harness = make_harness(policy=policy)

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
async def test_compatible_mode_ignores_broken_policy_configuration(make_harness):
    harness = make_harness(policy="not json", enforcement="compatible")

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
async def test_enforced_gate_uses_the_server_environment_policy(make_harness):
    harness = make_harness(environment="prod", enforcement="enforced")

    response = await harness.client.get(TODAY_URL, headers={**ios(25), "X-App-Environment": "stg"})

    assert response.status_code == 426
    assert response.json()["context"]["minimum_build"] == 90


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
    harness = make_harness(policy={"stg": {"android": POLICY["stg"]["android"]}}, enforcement="enforced")

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
