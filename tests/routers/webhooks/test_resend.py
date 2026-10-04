"""HTTP boundary for Resend email event webhooks (ROO-13). No live Resend calls."""

import json
import logging
import time
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from svix.webhooks import Webhook

from portal.config import settings
from portal.libs.logger import logger as app_logger
from portal.routers.webhooks import router as webhooks_router

SECRET = "whsec_" + "dGVzdC1zZWNyZXQtZm9yLXJvb3RlZC10ZXN0cw=="
URL = "/webhooks/resend/email-events"
OTP = "482913"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", SECRET)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router)
    return TestClient(app)


@pytest.fixture
def log_records(caplog):
    caplog.set_level(logging.DEBUG, logger=app_logger.name)
    return caplog


def _event(event_type: str, **data) -> bytes:
    body = {
        "type": event_type,
        "created_at": "2026-10-04T10:00:00.000Z",
        "data": {
            "email_id": "56761188-7520-42d8-8898-ff6fc54ce618",
            "from": "Rooted <account@rootedfaith.app>",
            "to": ["jane.doe@example.com"],
            "subject": f"Your Rooted code is {OTP}",
            **data,
        },
    }
    return json.dumps(body).encode()


def _signed_headers(payload: bytes, msg_id: str = "msg_2abc", secret: str = SECRET, timestamp: int | None = None) -> dict:
    ts = int(time.time()) if timestamp is None else timestamp
    signature = Webhook(secret).sign(msg_id, datetime.fromtimestamp(ts, tz=timezone.utc), payload.decode())
    return {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": signature, "content-type": "application/json"}


@pytest.mark.parametrize("event_type", ["email.failed", "email.bounced", "email.complained", "email.suppressed"])
def test_valid_selected_event_is_acknowledged(client, event_type) -> None:
    payload = _event(event_type)

    response = client.post(URL, content=payload, headers=_signed_headers(payload))

    assert response.status_code == 200


def test_duplicate_valid_delivery_is_acknowledged_both_times(client) -> None:
    payload = _event("email.bounced")
    headers = _signed_headers(payload)

    first = client.post(URL, content=payload, headers=headers)
    second = client.post(URL, content=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_valid_unsupported_event_is_acknowledged(client, log_records) -> None:
    payload = _event("email.delivered")

    response = client.post(URL, content=payload, headers=_signed_headers(payload))

    assert response.status_code == 200
    assert "email.bounced" not in log_records.text


def test_missing_signature_headers_are_rejected(client) -> None:
    response = client.post(URL, content=_event("email.failed"), headers={"content-type": "application/json"})

    assert response.status_code == 401


def test_wrong_secret_signature_is_rejected(client) -> None:
    payload = _event("email.failed")
    other = "whsec_" + "b3RoZXItc2VjcmV0LW90aGVyLXNlY3JldC1vdGhlcg=="

    response = client.post(URL, content=payload, headers=_signed_headers(payload, secret=other))

    assert response.status_code == 401


def test_tampered_payload_is_rejected(client) -> None:
    payload = _event("email.failed")
    headers = _signed_headers(payload)

    response = client.post(URL, content=payload.replace(b"email.failed", b"email.bounced"), headers=headers)

    assert response.status_code == 401


def test_stale_timestamp_is_rejected(client) -> None:
    payload = _event("email.failed")

    response = client.post(URL, content=payload, headers=_signed_headers(payload, timestamp=int(time.time()) - 3600))

    assert response.status_code == 401


def test_unconfigured_secret_is_a_receiver_failure_not_a_rejection(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")
    payload = _event("email.failed")

    response = client.post(URL, content=payload, headers=_signed_headers(payload))

    assert response.status_code == 503


def test_valid_signature_with_malformed_json_is_acknowledged(client) -> None:
    payload = b"not json"

    response = client.post(URL, content=payload, headers=_signed_headers(payload))

    assert response.status_code == 200


def test_diagnostics_keep_correlation_and_exclude_sensitive_data(client, log_records) -> None:
    payload = _event("email.bounced", bounce={"type": "Permanent", "message": f"mailbox full, code {OTP}"})

    client.post(URL, content=payload, headers=_signed_headers(payload, msg_id="msg_correlate_1"))

    text = log_records.text
    assert "email.bounced" in text
    assert "msg_correlate_1" in text
    assert "56761188-7520-42d8-8898-ff6fc54ce618" in text
    assert "jane.doe@example.com" not in text
    assert OTP not in text
    assert SECRET not in text
    assert "Your Rooted code" not in text
