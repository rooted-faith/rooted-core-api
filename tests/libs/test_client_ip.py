"""
Client IP resolution for rate limiting, request context, audit, and refresh tokens.
"""

import logging

import pytest
from starlette.requests import Request

from portal.libs.client_ip import resolved_client_ip


def _request(*, client_host: str | None = "203.0.113.10", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers or [],
        "client": (client_host, 12345) if client_host is not None else None,
        "server": ("test", 80),
    }
    return Request(scope)


def test_without_trusted_header_uses_connection_ip_and_ignores_x_forwarded_for():
    request = _request(headers=[(b"x-forwarded-for", b"198.51.100.1")])

    assert resolved_client_ip(request, trusted_header=None) == "203.0.113.10"


def test_trusted_header_with_valid_ip_is_used(caplog: pytest.LogCaptureFixture):
    request = _request(headers=[(b"true-client-ip", b"198.51.100.7")])

    with caplog.at_level(logging.WARNING):
        assert resolved_client_ip(request, trusted_header="True-Client-IP") == "198.51.100.7"

    assert "trusted client IP header" not in caplog.text.lower()


def test_trusted_header_missing_falls_back_to_connection_ip_and_warns(caplog: pytest.LogCaptureFixture):
    request = _request()

    with caplog.at_level(logging.WARNING):
        assert resolved_client_ip(request, trusted_header="True-Client-IP") == "203.0.113.10"

    assert "missing" in caplog.text.lower() or "absent" in caplog.text.lower()


def test_trusted_header_invalid_falls_back_to_connection_ip_and_warns(caplog: pytest.LogCaptureFixture):
    request = _request(headers=[(b"true-client-ip", b"not-an-ip")])

    with caplog.at_level(logging.WARNING):
        assert resolved_client_ip(request, trusted_header="True-Client-IP") == "203.0.113.10"

    assert "invalid" in caplog.text.lower()
