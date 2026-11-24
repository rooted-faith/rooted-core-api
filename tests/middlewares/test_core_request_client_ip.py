"""
CoreRequestMiddleware populates RequestContext.ip via trusted client IP resolution;
audit and refresh-token consumers record that IP.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from portal.application.audit.rbac_audit_service import RbacAuditService
from portal.config import settings
from portal.libs.consts.enums import OperationType
from portal.libs.contexts.request_context import get_request_context
from portal.middlewares.core_request import CoreRequestMiddleware
from portal.providers.refresh_token_provider import RefreshTokenProvider


class _FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _FakeContainer:
    def db_session(self) -> _FakeSession:
        return _FakeSession()


class _RecordingChain:
    def __init__(self, session: "_RecordingSession", kind: str):
        self._session = session
        self._kind = kind
        self._payload: dict[str, Any] = {}

    def values(self, *args: Any, **kwargs: Any) -> "_RecordingChain":
        if args and isinstance(args[0], dict):
            self._payload = dict(args[0])
        else:
            self._payload = dict(kwargs)
        return self

    def on_conflict_do_update(self, **kwargs: Any) -> "_RecordingChain":
        return self

    def where(self, *args: Any, **kwargs: Any) -> "_RecordingChain":
        return self

    async def execute(self) -> None:
        self._session.recorded.append((self._kind, self._payload))


class _RecordingSession:
    def __init__(self) -> None:
        self.recorded: list[tuple[str, dict[str, Any]]] = []

    def insert(self, model: Any) -> _RecordingChain:
        return _RecordingChain(self, f"insert:{getattr(model, '__name__', str(model))}")

    def update(self, model: Any) -> _RecordingChain:
        return _RecordingChain(self, f"update:{getattr(model, '__name__', str(model))}")


def _consumer_app(*, audit_events: list, refresh_session: _RecordingSession) -> FastAPI:
    app = FastAPI()
    app.container = _FakeContainer()
    app.add_middleware(CoreRequestMiddleware)

    @app.post("/audit")
    async def audit_probe():
        ctx = get_request_context()
        assert ctx is not None
        RbacAuditService().create_log(operation_type=OperationType.UPDATE, record_id=uuid4(), operation_code="role.update")
        return {"ip": ctx.ip, "client_ip": ctx.client_ip, "audit_ip": audit_events[-1].ip_address}

    @app.post("/refresh")
    async def refresh_probe():
        ctx = get_request_context()
        assert ctx is not None
        provider = RefreshTokenProvider(session=refresh_session)  # type: ignore[arg-type]
        await provider.issue(user_id=uuid4(), device_id=uuid4(), family_id=uuid4())
        token_inserts = [payload for kind, payload in refresh_session.recorded if kind.startswith("insert:AuthRefreshToken")]
        device_inserts = [payload for kind, payload in refresh_session.recorded if kind.startswith("insert:AuthDevice")]
        return {"ip": ctx.ip, "refresh_ip": token_inserts[-1]["ip"], "device_last_ip": device_inserts[-1]["last_ip"]}

    return app


def _stub_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _locale_detector(self, accept_language):
        return "en", None, ["en"]

    monkeypatch.setattr(CoreRequestMiddleware, "locale_detector", _locale_detector)


@pytest.mark.asyncio
async def test_forged_headers_do_not_change_audit_or_refresh_ip_without_trusted_header(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_SALT", "salt")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_PEPPER", "pepper")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_EXPIRE_DAYS", 7)
    _stub_locale(monkeypatch)

    audit_events: list = []
    monkeypatch.setattr("portal.application.audit.rbac_audit_service.publish_event_in_background", lambda event: audit_events.append(event))
    refresh_session = _RecordingSession()
    app = _consumer_app(audit_events=audit_events, refresh_session=refresh_session)
    transport = ASGITransport(app=app, client=("10.0.0.1", 12345))
    forge_headers = {"X-Forwarded-For": "1.2.3.4, 203.0.113.9", "X-Real-IP": "9.9.9.9"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        audit_response = await client.post("/audit", headers=forge_headers)
        refresh_response = await client.post("/refresh", headers=forge_headers)

    assert audit_response.status_code == 200
    assert audit_response.json() == {"ip": "10.0.0.1", "client_ip": "10.0.0.1", "audit_ip": "10.0.0.1"}
    assert refresh_response.status_code == 200
    assert refresh_response.json() == {"ip": "10.0.0.1", "refresh_ip": "10.0.0.1", "device_last_ip": "10.0.0.1"}


@pytest.mark.asyncio
async def test_trusted_header_is_written_to_audit_and_refresh_consumers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "True-Client-IP")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_SALT", "salt")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_PEPPER", "pepper")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_EXPIRE_DAYS", 7)
    _stub_locale(monkeypatch)

    audit_events: list = []
    monkeypatch.setattr("portal.application.audit.rbac_audit_service.publish_event_in_background", lambda event: audit_events.append(event))
    refresh_session = _RecordingSession()
    app = _consumer_app(audit_events=audit_events, refresh_session=refresh_session)
    transport = ASGITransport(app=app, client=("10.0.0.1", 12345))
    headers = {"True-Client-IP": "198.51.100.7", "X-Forwarded-For": "1.2.3.4"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        audit_response = await client.post("/audit", headers=headers)
        refresh_response = await client.post("/refresh", headers=headers)

    assert audit_response.status_code == 200
    assert audit_response.json()["audit_ip"] == "198.51.100.7"
    assert audit_response.json()["client_ip"] == "10.0.0.1"
    assert refresh_response.status_code == 200
    assert refresh_response.json() == {"ip": "198.51.100.7", "refresh_ip": "198.51.100.7", "device_last_ip": "198.51.100.7"}


@pytest.mark.asyncio
async def test_invalid_trusted_header_falls_back_to_connection_ip_for_consumers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "True-Client-IP")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_SALT", "salt")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_PEPPER", "pepper")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_EXPIRE_DAYS", 7)
    _stub_locale(monkeypatch)

    audit_events: list = []
    monkeypatch.setattr("portal.application.audit.rbac_audit_service.publish_event_in_background", lambda event: audit_events.append(event))
    refresh_session = _RecordingSession()
    app = _consumer_app(audit_events=audit_events, refresh_session=refresh_session)
    transport = ASGITransport(app=app, client=("10.0.0.1", 12345))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        audit_response = await client.post("/audit", headers={"True-Client-IP": "not-an-ip"})
        refresh_response = await client.post("/refresh", headers={"True-Client-IP": "1.2.3.4, 5.6.7.8"})

    assert audit_response.json()["audit_ip"] == "10.0.0.1"
    assert refresh_response.json()["refresh_ip"] == "10.0.0.1"
    assert refresh_response.json()["device_last_ip"] == "10.0.0.1"
