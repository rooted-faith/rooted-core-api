"""Error reporting boundary: what leaves the process when something raises. No live Sentry calls."""

import json

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from portal import main
from portal.config import settings


class CapturingTransport(Transport):
    def __init__(self):
        super().__init__()
        self.payloads: list[str] = []

    def capture_envelope(self, envelope) -> None:
        self.payloads.extend(json.dumps(item.payload.json) for item in envelope.items)


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    transport = CapturingTransport()
    real_init = sentry_sdk.init

    def init_without_network(**options) -> None:
        real_init(**{**options, "transport": transport, "integrations": [], "default_integrations": False, "auto_enabling_integrations": False})

    monkeypatch.setattr(settings, "SENTRY_URL", "https://public@sentry.invalid/1")
    monkeypatch.setattr(sentry_sdk, "init", init_without_network)
    main.setup_tracing()
    yield transport
    real_init()


def test_error_reports_never_contain_local_variables(transport: CapturingTransport) -> None:
    try:
        test_passcode = "".join(["482", "913"])
        raise ConnectionError("storage down")
    except ConnectionError as error:
        sentry_sdk.capture_exception(error)

    assert any("storage down" in payload for payload in transport.payloads)
    assert all(test_passcode not in payload for payload in transport.payloads)


def test_error_reports_mask_the_submitted_code_and_still_mask_passwords(transport: CapturingTransport) -> None:
    sentry_sdk.capture_event({"message": "failed", "request": {"data": {"email": "a@example.com", "code": "482913", "password": "hunter2"}}})

    assert any("failed" in payload for payload in transport.payloads)
    assert all("482913" not in payload and "hunter2" not in payload for payload in transport.payloads)
