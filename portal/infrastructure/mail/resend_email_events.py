"""
Resend email event webhooks: Svix signature verification and redacted diagnostics.

Resend stays the suppression source of truth. Nothing here persists events.
"""

import json
from dataclasses import dataclass
from typing import Mapping

from svix.webhooks import Webhook, WebhookVerificationError

from portal.libs.logger import logger

HANDLED_EVENT_TYPES = frozenset({"email.failed", "email.bounced", "email.complained", "email.suppressed"})


class ResendWebhookNotConfiguredError(Exception):
    """The signing secret is missing, so no delivery can be verified."""


class InvalidResendSignatureError(Exception):
    """The signature headers are missing, stale, or do not match the raw payload."""


@dataclass(frozen=True)
class ResendEmailEvent:
    event_type: str
    message_id: str
    email_id: str | None
    recipient_count: int
    recipients: tuple[str, ...]


def redact_email(address: str) -> str:
    """Keep the first character and the domain, e.g. ``j***@example.com``."""
    local, sep, domain = address.partition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


class ResendEmailEventReceiver:
    def __init__(self, signing_secret: str):
        self._signing_secret = signing_secret

    def receive(self, payload: bytes, headers: Mapping[str, str]) -> None:
        """Verify the exact raw payload, then log redacted diagnostics for selected events."""
        if not self._signing_secret:
            raise ResendWebhookNotConfiguredError()
        try:
            Webhook(self._signing_secret).verify(payload, dict(headers))
        except WebhookVerificationError as exc:
            raise InvalidResendSignatureError() from exc

        event = self._parse(payload, headers.get("svix-id", ""))
        if event is None:
            return
        logger.warning(
            "resend_email_event type=%s svix_id=%s email_id=%s recipient_count=%d recipients=%s",
            event.event_type,
            event.message_id,
            event.email_id,
            event.recipient_count,
            ",".join(event.recipients),
        )

    @staticmethod
    def _parse(payload: bytes, message_id: str) -> ResendEmailEvent | None:
        try:
            parsed = json.loads(payload)
        except ValueError:
            # Genuine signature over a body that is not JSON: nothing to observe, do not retry.
            return None
        if not isinstance(parsed, dict) or parsed.get("type") not in HANDLED_EVENT_TYPES:
            return None
        data = parsed.get("data")
        data = data if isinstance(data, dict) else {}
        raw_to = data.get("to")
        to = [item for item in raw_to if isinstance(item, str)] if isinstance(raw_to, list) else []
        email_id = data.get("email_id")
        return ResendEmailEvent(
            event_type=parsed["type"],
            message_id=message_id,
            email_id=email_id if isinstance(email_id, str) else None,
            recipient_count=len(to),
            recipients=tuple(redact_email(item) for item in to),
        )
