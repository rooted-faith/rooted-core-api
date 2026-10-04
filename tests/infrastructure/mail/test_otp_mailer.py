"""
Resend OTP mailer seam: observable provider request content, locale rendering, failure mapping.
No real email is sent; httpx is given a mock transport.
"""

import json

import httpx
import pytest

from portal.config import settings
from portal.domain.auth.ports import OtpDeliveryError
from portal.infrastructure.mail.otp_mailer import OtpMailer


def _mailer(handler, api_key: str = "re_test") -> OtpMailer:
    return OtpMailer(api_key=api_key, sender="Rooted <account@rootedfaith.app>", transport=httpx.MockTransport(handler))


def _capture():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "email_1"})

    return seen, handler


@pytest.mark.asyncio
async def test_sends_html_and_text_from_the_agreed_sender_without_replies_or_links():
    seen, handler = _capture()

    await _mailer(handler).send_otp("jay@example.com", "123456", locale="en")

    request = seen[0]
    body = json.loads(request.content)
    assert request.url.path == "/emails"
    assert request.headers["Authorization"] == "Bearer re_test"
    assert body["from"] == "Rooted <account@rootedfaith.app>"
    assert body["to"] == ["jay@example.com"]
    assert "123456" in body["html"] and "123456" in body["text"]
    assert not {"reply_to", "replyTo", "cc", "bcc", "tags", "headers"} & set(body)
    for part in (body["html"], body["text"]):
        assert "http://" not in part and "https://" not in part and "<img" not in part and "<a " not in part


@pytest.mark.asyncio
async def test_english_message_states_validity_and_ignore_guidance():
    seen, handler = _capture()

    await _mailer(handler).send_otp("jay@example.com", "123456", locale="en")

    body = json.loads(seen[0].content)
    assert "123456" in body["subject"]
    assert f"{settings.OTP_CODE_EXPIRE_MINUTES} minutes" in body["text"]
    assert "ignore this email" in body["text"]
    assert '<html lang="en">' in body["html"]


@pytest.mark.asyncio
async def test_traditional_chinese_message_states_validity_and_ignore_guidance():
    seen, handler = _capture()

    await _mailer(handler).send_otp("jay@example.com", "123456", locale="zh-TW")

    body = json.loads(seen[0].content)
    assert "驗證碼" in body["subject"]
    assert f"{settings.OTP_CODE_EXPIRE_MINUTES} 分鐘" in body["text"]
    assert "忽略" in body["text"]
    assert '<html lang="zh-Hant">' in body["html"]


@pytest.mark.asyncio
async def test_unresolved_locale_falls_back_to_english():
    seen, handler = _capture()

    await _mailer(handler).send_otp("jay@example.com", "123456", locale=None)

    assert "Your Rooted verification code" in json.loads(seen[0].content)["subject"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 422, 429, 500])
async def test_provider_rejection_raises_delivery_error(status: int):
    mailer = _mailer(lambda request: httpx.Response(status, json={"message": "nope"}))

    with pytest.raises(OtpDeliveryError):
        await mailer.send_otp("jay@example.com", "123456", locale="en")


@pytest.mark.asyncio
async def test_network_failure_raises_delivery_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(OtpDeliveryError):
        await _mailer(handler).send_otp("jay@example.com", "123456", locale="en")


@pytest.mark.asyncio
async def test_missing_api_key_outside_dev_fails_delivery(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "IS_DEV", False)

    with pytest.raises(OtpDeliveryError):
        await _mailer(lambda request: httpx.Response(200), api_key="").send_otp("jay@example.com", "123456", locale="en")
