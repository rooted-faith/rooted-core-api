"""
Request/verify against a real Redis: TTL and one-time consumption that in-memory stubs cannot prove.
Set TEST_REDIS_URL to an isolated Redis; skipped otherwise. Keys use a unique prefix and are removed afterwards.
"""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError

from portal.application.auth.commands import AppOtpRequestCommand, AppOtpVerifyCommand
from portal.config import settings
from portal.domain.auth.constants import OtpDeliveryMode
from portal.domain.auth.entities import OtpChallenge
from portal.domain.auth.otp_test_policy import OtpTestPolicy
from portal.exceptions.responses import TooManyRequestsException, UnauthorizedException
from portal.infrastructure.cache.otp_token_cache import OtpTokenCache
from portal.libs.database import RedisPool
from tests.application.auth.test_app_auth_service import StubOtpTestPolicySource, _build_service

TESTER = "alice@test.example.com"


def _policy(enabled: bool = True) -> OtpTestPolicy:
    return OtpTestPolicy(project_id="rooted-app-dev", test_mode_enabled=enabled, allowlist=("*@test.example.com",))


class ShortLivedOtpTokenCache(OtpTokenCache):
    """Real storage with a one-second lifetime so that real expiry is observable."""

    async def store(self, email: str, challenge: OtpChallenge, ttl_seconds: int) -> None:
        await super().store(email, challenge, 1)


@pytest_asyncio.fixture
async def redis_client(monkeypatch: pytest.MonkeyPatch):
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL is not set")
    prefix = f"rooted-otp-test-{uuid4().hex}"
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    monkeypatch.setattr(settings, "REDIS_URL", url)
    monkeypatch.setattr(settings, "ENV", "stg")
    monkeypatch.setattr(settings, "OTP_FIXED_CODE", "")
    client: Redis = from_url(url, encoding="utf-8", decode_responses=True)
    try:
        await client.ping()
    except RedisError as error:
        await client.aclose()
        pytest.skip(f"Redis not reachable: {error}")
    yield client
    keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
    if keys:
        await client.delete(*keys)
    await client.aclose()


@pytest_asyncio.fixture
async def redis_pool(redis_client: Redis):
    pool = RedisPool()
    yield pool
    await pool.create().aclose()


async def _request(service, email: str = TESTER):
    return await service.request_otp(AppOtpRequestCommand(email=email))


async def _verify(service, email: str = TESTER, code: str = "123456"):
    return await service.verify_otp(AppOtpVerifyCommand(email=email, code=code))


@pytest.mark.asyncio
async def test_fixed_challenge_is_stored_hashed_with_the_configured_lifetime(redis_client: Redis, redis_pool: RedisPool):
    service, *_rest = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))

    await _request(service)

    key = f"{settings.APP_NAME}:otp:{TESTER}"
    assert "123456" not in await redis_client.get(key)
    assert 0 < await redis_client.ttl(key) <= settings.OTP_CODE_EXPIRE_MINUTES * 60


@pytest.mark.asyncio
async def test_every_challenge_key_expires_on_its_own(redis_client: Redis, redis_pool: RedisPool):
    service, *_rest = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))

    await _request(service)
    await _request(service, "jay@example.com")

    keys = [key async for key in redis_client.scan_iter(match=f"{settings.APP_NAME}:*")]
    assert keys
    for key in keys:
        assert await redis_client.ttl(key) > 0, key


@pytest.mark.asyncio
@pytest.mark.parametrize("email", [TESTER, "jay@example.com"], ids=["fixed", "email"])
async def test_challenge_expires_in_both_modes(redis_pool: RedisPool, email: str):
    service, *_rest, mailer, _store = _build_service(StubOtpTestPolicySource(_policy()), ShortLivedOtpTokenCache(redis_pool))
    await _request(service, email)
    code = mailer.sent[-1][1] if mailer.sent else "123456"

    await asyncio.sleep(1.2)

    with pytest.raises(UnauthorizedException):
        await _verify(service, email, code)


@pytest.mark.asyncio
@pytest.mark.parametrize("email", [TESTER, "jay@example.com"], ids=["fixed", "email"])
async def test_concurrent_verification_consumes_the_challenge_exactly_once(redis_pool: RedisPool, email: str):
    service, *_rest, mailer, _store = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))
    await _request(service, email)
    code = mailer.sent[-1][1] if mailer.sent else "123456"

    outcomes = await asyncio.gather(*(_verify(service, email, code) for _ in range(20)), return_exceptions=True)

    assert len([outcome for outcome in outcomes if not isinstance(outcome, Exception)]) == 1
    assert len([outcome for outcome in outcomes if isinstance(outcome, UnauthorizedException)]) == 19


@pytest.mark.asyncio
async def test_wrong_code_keeps_the_challenge(redis_pool: RedisPool):
    service, *_rest = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))
    await _request(service)

    with pytest.raises(UnauthorizedException):
        await _verify(service, code="999999")

    assert (await _verify(service)).member.email == TESTER


@pytest.mark.asyncio
async def test_withdrawal_removes_fixed_challenges_but_keeps_emailed_ones(redis_pool: RedisPool):
    source = StubOtpTestPolicySource(_policy())
    service, *_rest, mailer, _store = _build_service(source, OtpTokenCache(redis_pool))
    await _request(service)
    await _request(service, "jay@example.com")
    emailed_code = mailer.sent[-1][1]

    source.policy = _policy(enabled=False)
    await _request(service, "someone@elsewhere.example")
    source.policy = _policy()

    with pytest.raises(UnauthorizedException):
        await _verify(service)
    assert (await _verify(service, "jay@example.com", emailed_code)).member.email == "jay@example.com"


@pytest.mark.asyncio
async def test_withdrawal_observed_by_one_instance_applies_to_every_instance(redis_pool: RedisPool):
    issuing, *_rest = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))
    observing, *_rest = _build_service(StubOtpTestPolicySource(_policy(enabled=False)), OtpTokenCache(redis_pool))
    await _request(issuing)

    await _request(observing, "someone@elsewhere.example")

    with pytest.raises(UnauthorizedException):
        await _verify(issuing)


@pytest.mark.asyncio
async def test_emailed_challenge_replacing_a_fixed_one_is_not_withdrawn_with_it(redis_pool: RedisPool):
    source = StubOtpTestPolicySource(_policy())
    service, *_rest, mailer, _store = _build_service(source, OtpTokenCache(redis_pool))
    await _request(service)
    source.policy = None
    await _request(service)
    source.policy = _policy(enabled=False)
    await _request(service, "someone@elsewhere.example")

    emailed_code = mailer.sent[0][1]
    assert mailer.sent[0][0] == TESTER
    assert (await _verify(service, code=emailed_code)).member.email == TESTER


@pytest.mark.asyncio
async def test_challenge_emailed_before_this_release_is_still_redeemable(redis_client: Redis, redis_pool: RedisPool):
    service, *_rest = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))
    # Before challenge origin existed, the key held the bare hash of an emailed code.
    bare_hash = OtpChallenge.of("jay@example.com", "482913", OtpDeliveryMode.EMAIL).code_hash
    await redis_client.set(f"{settings.APP_NAME}:otp:jay@example.com", bare_hash, ex=600)

    assert (await _verify(service, "jay@example.com", "482913")).member.email == "jay@example.com"


@pytest.mark.asyncio
async def test_request_quota_applies_to_fixed_mode(redis_pool: RedisPool):
    service, *_rest = _build_service(StubOtpTestPolicySource(_policy()), OtpTokenCache(redis_pool))
    for _ in range(settings.OTP_REQUEST_MAX_PER_WINDOW):
        await _request(service)

    with pytest.raises(TooManyRequestsException):
        await _request(service)
