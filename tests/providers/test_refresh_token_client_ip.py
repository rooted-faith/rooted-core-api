"""
Refresh token / device records persist RequestContext.ip from trusted resolution.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from portal.application.auth.results import HeaderInfo
from portal.libs.contexts.request_context import RequestContext, reset_request_context, set_request_context
from portal.providers.refresh_token_provider import RefreshTokenProvider


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


@pytest.mark.asyncio
async def test_issue_persists_request_context_ip_on_device_and_refresh_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_SALT", "salt")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_PEPPER", "pepper")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_EXPIRE_DAYS", 7)

    token = set_request_context(RequestContext(ip="10.0.0.1", client_ip="10.0.0.1", headers=HeaderInfo(user_agent="pytest-agent")))
    session = _RecordingSession()
    try:
        provider = RefreshTokenProvider(session=session)  # type: ignore[arg-type]
        await provider.issue(user_id=uuid4(), device_id=uuid4(), family_id=uuid4())
    finally:
        reset_request_context(token)

    device_inserts = [payload for kind, payload in session.recorded if kind.startswith("insert:AuthDevice")]
    token_inserts = [payload for kind, payload in session.recorded if kind.startswith("insert:AuthRefreshToken")]
    assert device_inserts
    assert token_inserts
    assert device_inserts[0]["last_ip"] == "10.0.0.1"
    assert token_inserts[0]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_issue_persists_trusted_resolved_ip_when_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_SALT", "salt")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_HASH_PEPPER", "pepper")
    monkeypatch.setattr("portal.providers.refresh_token_provider.settings.REFRESH_TOKEN_EXPIRE_DAYS", 7)

    token = set_request_context(RequestContext(ip="198.51.100.7", client_ip="10.0.0.1", headers=HeaderInfo(user_agent="pytest-agent")))
    session = _RecordingSession()
    try:
        provider = RefreshTokenProvider(session=session)  # type: ignore[arg-type]
        await provider.issue(user_id=uuid4(), device_id=uuid4(), family_id=uuid4())
    finally:
        reset_request_context(token)

    device_inserts = [payload for kind, payload in session.recorded if kind.startswith("insert:AuthDevice")]
    token_inserts = [payload for kind, payload in session.recorded if kind.startswith("insert:AuthRefreshToken")]
    assert device_inserts[0]["last_ip"] == "198.51.100.7"
    assert token_inserts[0]["ip"] == "198.51.100.7"
