"""
Deliver one-time passcodes through Resend (ADR 0008, ADR 0009).
"""

import logging
from typing import Optional

import httpx

from portal.config import settings
from portal.domain.auth.ports import OtpDeliveryError
from portal.infrastructure.mail.otp_email_content import render_otp_email

logger = logging.getLogger(__name__)

RESEND_BASE_URL = "https://api.resend.com"


class OtpMailer:
    """Send the passcode email in the caller-resolved locale; raise OtpDeliveryError when Resend cannot accept it."""

    def __init__(
        self, api_key: Optional[str] = None, sender: Optional[str] = None, timeout_sec: float = 10.0, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._api_key = settings.RESEND_API_KEY if api_key is None else api_key
        self._sender = sender or settings.OTP_EMAIL_SENDER
        self._timeout_sec = timeout_sec
        self._transport = transport

    async def send_otp(self, email: str, code: str, *, locale: Optional[str]) -> None:
        if not self._api_key:
            if settings.IS_DEV:
                # Local/dev without Resend credentials: capture the code from logs instead of failing.
                logger.info("RESEND_API_KEY unset; OTP for %s in locale %s (code: %s)", email, locale, code)
                return
            raise OtpDeliveryError("RESEND_API_KEY is not configured")

        content = render_otp_email(code, locale=locale, expire_minutes=settings.OTP_CODE_EXPIRE_MINUTES)
        payload = {"from": self._sender, "to": [email], "subject": content.subject, "html": content.html, "text": content.text}
        try:
            async with httpx.AsyncClient(base_url=RESEND_BASE_URL, timeout=self._timeout_sec, transport=self._transport) as client:
                response = await client.post("/emails", json=payload, headers={"Authorization": f"Bearer {self._api_key}"})
        except httpx.HTTPError as exc:
            raise OtpDeliveryError(f"Resend request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise OtpDeliveryError(f"Resend rejected the message: HTTP {response.status_code}")
