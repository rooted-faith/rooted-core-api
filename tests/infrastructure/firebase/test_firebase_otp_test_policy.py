"""
Test passcode policy seam: real SDK template evaluation over controlled server templates and a controlled clock.
No live Firebase calls; these tests say nothing about live project permissions.
"""

import asyncio
import json
import logging
from typing import Any, Optional

import firebase_admin
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from firebase_admin import remote_config

from portal.application.auth.commands import AppOtpRequestCommand
from portal.config import settings
from portal.domain.auth.constants import OtpDeliveryMode
from portal.infrastructure.firebase.firebase_otp_test_policy import FirebaseOtpTestPolicy
from portal.providers.firebase_push_gateway import FirebasePushGateway
from tests.application.auth.test_app_auth_service import _build_service

TESTER = "alice@test.example.com"
ALLOWLIST = '["*@test.example.com"]'
_PRIVATE_KEY = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    .decode()
)


def _credentials(project_id: str = "rooted-app-dev") -> dict:
    return {
        "type": "service_account",
        "project_id": project_id,
        "private_key": _PRIVATE_KEY,
        "client_email": f"backend@{project_id}.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _template(flag: Optional[str] = "true", allowlist: Optional[str] = ALLOWLIST) -> dict[str, Any]:
    parameters = {}
    if flag is not None:
        parameters["otp_test_mode_enabled"] = {"defaultValue": {"value": flag}, "valueType": "BOOLEAN"}
    if allowlist is not None:
        parameters["otp_test_allowlist"] = {"defaultValue": {"value": allowlist}, "valueType": "JSON"}
    return {"parameters": parameters, "conditions": []}


class FakeFirebase:
    """Stands in for the server template endpoint; serves one whole template per load."""

    def __init__(self):
        self.template: dict[str, Any] = _template()
        self.error: Optional[Exception] = None
        self.hang = False
        self.loaded_projects: list[str] = []
        self.now = 1000.0
        self.load_duration = 0.0

    def clock(self) -> float:
        return self.now

    async def get_server_template(self, app=None, default_config=None):
        self.loaded_projects.append(app.project_id)
        await asyncio.sleep(3600 if self.hang else 0)
        self.now += self.load_duration
        if self.error is not None:
            raise self.error
        return remote_config.init_server_template(app=app, default_config=default_config, template_data_json=json.dumps(self.template))


def _delete_all_apps() -> None:
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)


@pytest.fixture
def firebase(monkeypatch: pytest.MonkeyPatch):
    _delete_all_apps()
    fake = FakeFirebase()
    monkeypatch.setattr(remote_config, "get_server_template", fake.get_server_template)
    yield fake
    _delete_all_apps()


def _source(firebase: FakeFirebase, credentials: Optional[dict] = None, **kwargs) -> FirebaseOtpTestPolicy:
    return FirebaseOtpTestPolicy(credentials_dict=_credentials() if credentials is None else credentials, clock=firebase.clock, **kwargs)


async def _permits(source: FirebaseOtpTestPolicy, email: str = TESTER) -> bool:
    policy = await source.current()
    return policy is not None and policy.permits(email)


@pytest.mark.asyncio
async def test_reads_flag_and_allowlist_from_the_dev_project(firebase: FakeFirebase):
    policy = await _source(firebase).current()

    assert policy.project_id == "rooted-app-dev"
    assert policy.permits(TESTER)
    assert not policy.permits("alice@example.com")
    assert firebase.loaded_projects == ["rooted-app-dev"]


@pytest.mark.asyncio
async def test_remote_policy_drives_the_selected_delivery_mode(firebase: FakeFirebase, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ENV", "stg")
    service, *_rest = _build_service(_source(firebase))

    assert (await service.request_otp(AppOtpRequestCommand(email=TESTER))).delivery_mode is OtpDeliveryMode.FIXED
    firebase.template = _template(flag="false")
    firebase.now += 60
    assert (await service.request_otp(AppOtpRequestCommand(email=TESTER))).delivery_mode is OtpDeliveryMode.EMAIL


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [{"flag": None}, {"allowlist": None}, {"flag": None, "allowlist": None}])
async def test_missing_parameters_use_the_disabled_defaults(firebase: FakeFirebase, missing: dict):
    firebase.template = _template(**missing)

    assert not await _permits(_source(firebase))


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["false", "", "1", "yes", "on", "TRUE ", "enabled", "null"])
async def test_only_a_literal_true_enables_test_mode(firebase: FakeFirebase, flag: str):
    firebase.template = _template(flag=flag)

    assert not await _permits(_source(firebase))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allowlist",
    [
        "[]",
        "",
        "null",
        "not json",
        '"*@test.example.com"',
        '{"rules": ["*@test.example.com"]}',
        '["*@test.example.com", 7]',
        '["*@test.example.com", null]',
        '["*@test.example.com", ["tester@example.com"]]',
        '["*@test.example.com", "*"]',
        '["*@test.example.com"',
        "[" * 100_000,
    ],
    ids=lambda value: value[:40],
)
async def test_empty_or_malformed_allowlist_grants_nothing(firebase: FakeFirebase, caplog: pytest.LogCaptureFixture, allowlist: str):
    firebase.template = _template(allowlist=allowlist)

    assert not await _permits(_source(firebase))
    assert ("otp_test_allowlist" in caplog.text) is (allowlist != "[]")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "template",
    [
        {"parameters": None, "conditions": []},
        {"parameters": {"otp_test_mode_enabled": "true"}, "conditions": []},
        {"parameters": {"otp_test_mode_enabled": {"defaultValue": {"useInAppDefault": True}}}, "conditions": []},
    ],
)
async def test_malformed_template_grants_nothing(firebase: FakeFirebase, template: dict):
    firebase.template = template

    assert not await _permits(_source(firebase))


@pytest.mark.asyncio
async def test_fresh_snapshot_is_reused_until_exactly_sixty_seconds(firebase: FakeFirebase):
    source = _source(firebase)
    first = await source.current()
    firebase.template = _template(flag="false")

    firebase.now += 59.9
    assert await source.current() is first
    firebase.now += 0.1
    assert not await _permits(source)
    assert len(firebase.loaded_projects) == 2


@pytest.mark.asyncio
async def test_flag_and_allowlist_always_come_from_the_same_template(firebase: FakeFirebase):
    source = _source(firebase)
    assert await _permits(source)

    firebase.template = _template(allowlist='["other@example.com"]')
    assert await _permits(source)
    assert not await _permits(source, "other@example.com")

    firebase.now += 60
    assert not await _permits(source)
    assert await _permits(source, "other@example.com")


@pytest.mark.asyncio
async def test_connection_failure_uses_the_snapshot_only_while_fresh_and_never_renews_it(firebase: FakeFirebase):
    source = _source(firebase)
    assert await _permits(source)
    firebase.error = ConnectionError("down")

    firebase.now += 59
    assert await _permits(source)
    for _ in range(5):
        firebase.now += 20
        assert await source.current() is None

    firebase.error = None
    firebase.now += 20
    assert await _permits(source)


@pytest.mark.asyncio
async def test_freshness_counts_from_when_the_load_started(firebase: FakeFirebase):
    firebase.load_duration = 4
    source = _source(firebase)
    assert await _permits(source)

    firebase.error = ConnectionError("down")
    firebase.now += 56
    assert await source.current() is None


@pytest.mark.asyncio
async def test_initial_failure_is_unusable_and_not_retried_on_every_request(firebase: FakeFirebase):
    firebase.error = PermissionError("denied")
    source = _source(firebase)

    for _ in range(10):
        assert await source.current() is None
    assert len(firebase.loaded_projects) == 1

    firebase.error = None
    firebase.now += 10
    assert await _permits(source)


@pytest.mark.asyncio
async def test_hanging_load_is_abandoned(firebase: FakeFirebase):
    firebase.hang = True

    assert await _source(firebase, load_timeout_seconds=0.01).current() is None


@pytest.mark.asyncio
async def test_invalid_template_replaces_a_previously_valid_snapshot(firebase: FakeFirebase):
    source = _source(firebase)
    assert await _permits(source)

    firebase.template = _template(allowlist='["*"]')
    firebase.now += 60
    assert await source.current() is None


@pytest.mark.asyncio
async def test_concurrent_requests_share_one_load(firebase: FakeFirebase):
    source = _source(firebase)

    policies = await asyncio.gather(*(source.current() for _ in range(20)))

    assert len(firebase.loaded_projects) == 1
    assert all(policy is policies[0] for policy in policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", ["rooted-app-prod", "another-project"])
async def test_other_projects_are_never_loaded(firebase: FakeFirebase, project_id: str):
    assert await _source(firebase, _credentials(project_id)).current() is None
    assert firebase.loaded_projects == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "credentials",
    [{}, {"type": "service_account"}, {"type": "authorized_user"}, {**_credentials(), "private_key": "broken"}],
    ids=lambda value: str(sorted(value)),
)
async def test_missing_or_unusable_credentials_are_unusable(firebase: FakeFirebase, credentials: dict):
    assert await _source(firebase, credentials).current() is None
    assert firebase.loaded_projects == []


@pytest.mark.asyncio
async def test_environment_project_override_cannot_change_the_selected_project(firebase: FakeFirebase, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "rooted-app-dev")
    monkeypatch.setenv("FIREBASE_CONFIG", '{"projectId": "rooted-app-dev"}')

    assert await _source(firebase, _credentials("rooted-app-prod")).current() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("push_first", [True, False])
async def test_push_keeps_its_own_default_app_regardless_of_initialization_order(firebase: FakeFirebase, push_first: bool):
    source = _source(firebase)
    if push_first:
        FirebasePushGateway(_credentials("push-project"))
    assert await _permits(source)
    if not push_first:
        FirebasePushGateway(_credentials("push-project"))

    assert firebase_admin.get_app().project_id == "push-project"
    assert firebase.loaded_projects == ["rooted-app-dev"]


@pytest.mark.asyncio
async def test_diagnostics_expose_neither_the_allowlist_nor_credentials(firebase: FakeFirebase, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    firebase.template = _template(allowlist='["secret-tester@example.com", "*"]')
    await _source(firebase).current()
    firebase.error = RuntimeError("secret-tester@example.com rejected with token abc")
    await _source(firebase).current()
    await _source(firebase, {**_credentials(), "private_key": "leaky-private-key"}).current()

    assert "otp_test_allowlist" in caplog.text
    assert "RuntimeError" in caplog.text
    for secret in ("secret-tester", "token abc", "leaky-private-key"):
        assert secret not in caplog.text
