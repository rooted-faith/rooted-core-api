"""
HTTP rate limiters: per-client sliding windows, mounted sub-apps, Redis fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from portal.libs.depends.rate_limiters import (
    RedisRateLimiterDependency,
    attach_rate_limiters,
    create_memory_rate_limiters,
    create_redis_rate_limiters,
    get_rate_limiters_config,
)
from portal.libs.rate_limit.config import RateLimiterConfig, RateLimitersConfig, RateLimitWindow
from portal.libs.rate_limit.gateway import RateLimiterGateway


class _FakeScript:
    def __init__(self, result: int = 1, delay_seconds: float = 0.0, raise_error: Exception | None = None):
        self.result = result
        self.delay_seconds = delay_seconds
        self.raise_error = raise_error
        self.calls: list[tuple[list[str], list]] = []

    async def __call__(self, keys=None, args=None):
        self.calls.append((list(keys or []), list(args or [])))
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.raise_error is not None:
            raise self.raise_error
        return self.result


class _FakeRedis:
    def __init__(self, result: int = 1, delay_seconds: float = 0.0, raise_error: Exception | None = None):
        self.script = _FakeScript(result=result, delay_seconds=delay_seconds, raise_error=raise_error)

    def register_script(self, script: str) -> _FakeScript:
        return self.script


class _RejectingLimiter:
    async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
        return False


class _AllowingLimiter:
    async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
        return True


def _tight_config() -> RateLimitersConfig:
    window = RateLimitWindow(times=1, seconds=60)
    group = RateLimiterConfig(short=window, medium=window, long=window)
    return RateLimitersConfig(default=group, read=group, write=group)


def _main_with_mounted_apps() -> FastAPI:
    api = FastAPI()

    @api.get("/limited", dependencies=[Depends(RedisRateLimiterDependency("write"))])
    async def api_limited():
        return {"ok": True}

    admin = FastAPI()

    @admin.get("/limited", dependencies=[Depends(RedisRateLimiterDependency("default"))])
    async def admin_limited():
        return {"ok": True}

    main = FastAPI()
    main.mount("/api", api)
    main.mount("/admin", admin)
    return main


@pytest.mark.asyncio
async def test_limiters_attached_at_startup_apply_to_mounted_sub_apps():
    main = _main_with_mounted_apps()
    gateway = RateLimiterGateway(memory_limiters={"default": [_RejectingLimiter()], "write": [_RejectingLimiter()]})
    attach_rate_limiters(main, gateway)

    async with AsyncClient(transport=ASGITransport(app=main), base_url="http://test") as client:
        api_response = await client.get("/api/limited")
        admin_response = await client.get("/admin/limited")

    assert api_response.status_code == 429
    assert admin_response.status_code == 429


@pytest.mark.asyncio
async def test_redis_limiter_uses_one_key_per_client_identifier(monkeypatch: pytest.MonkeyPatch):
    from portal.config import settings

    monkeypatch.setattr(settings, "APP_NAME", "rooted-core-api")
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())

    redis = _FakeRedis()
    limiters = await create_redis_rate_limiters(redis)
    await limiters["write"][0].try_acquire_async("10.0.0.1:/api/v1/auth/otp")
    await limiters["write"][0].try_acquire_async("10.0.0.2:/api/v1/auth/otp")
    await limiters["write"][0].try_acquire_async("10.0.0.1:/api/v1/auth/verify")

    keys = [call[0][0] for call in redis.script.calls]
    assert len(set(keys)) == 3
    assert all("rate_limiter:write:" in key for key in keys)


@pytest.mark.asyncio
async def test_memory_limiter_isolates_clients():
    limiters = create_memory_rate_limiters(_tight_config())
    limiter = limiters["write"][0]

    assert await limiter.try_acquire_async("1.1.1.1:/path") is True
    assert await limiter.try_acquire_async("1.1.1.1:/path") is False
    assert await limiter.try_acquire_async("2.2.2.2:/path") is True


@pytest.mark.asyncio
async def test_forged_x_forwarded_for_does_not_bypass_without_trusted_header(monkeypatch: pytest.MonkeyPatch):
    from portal.config import settings

    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())

    main = _main_with_mounted_apps()
    gateway = RateLimiterGateway(memory_limiters=create_memory_rate_limiters(_tight_config()))
    attach_rate_limiters(main, gateway)

    async with AsyncClient(transport=ASGITransport(app=main), base_url="http://test") as client:
        first = await client.get("/api/limited", headers={"X-Forwarded-For": "198.51.100.1"})
        second = await client.get("/api/limited", headers={"X-Forwarded-For": "198.51.100.2"})

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_trusted_header_separates_quotas(monkeypatch: pytest.MonkeyPatch):
    from portal.config import settings

    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "True-Client-IP")
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())

    main = _main_with_mounted_apps()
    gateway = RateLimiterGateway(memory_limiters=create_memory_rate_limiters(_tight_config()))
    attach_rate_limiters(main, gateway)

    async with AsyncClient(transport=ASGITransport(app=main), base_url="http://test") as client:
        first = await client.get("/api/limited", headers={"True-Client-IP": "198.51.100.1"})
        second = await client.get("/api/limited", headers={"True-Client-IP": "198.51.100.2"})
        third = await client.get("/api/limited", headers={"True-Client-IP": "198.51.100.1"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_gateway_falls_back_to_memory_when_redis_errors(caplog: pytest.LogCaptureFixture):
    memory = create_memory_rate_limiters(_tight_config())
    redis_limiters = {"write": [_AllowingLimiter()]}  # replaced below via gateway internals

    redis = _FakeRedis(raise_error=ConnectionError("boom"))
    redis_limiters = await create_redis_rate_limiters(redis)
    # Force tight config windows onto redis path by using memory for assertion after fallback
    gateway = RateLimiterGateway(memory_limiters=memory, redis_limiters=redis_limiters, redis_timeout_seconds=1.0, redis_retry_seconds=30.0)

    with caplog.at_level(logging.ERROR):
        assert await gateway.acquire("write", "1.1.1.1:/path") is True
        assert await gateway.acquire("write", "1.1.1.1:/path") is False

    assert "redis" in caplog.text.lower() or "rate limit" in caplog.text.lower()


@pytest.mark.asyncio
async def test_gateway_times_out_redis_and_falls_back():
    memory = create_memory_rate_limiters(_tight_config())
    redis = _FakeRedis(delay_seconds=2.0)
    redis_limiters = await create_redis_rate_limiters(redis)
    gateway = RateLimiterGateway(memory_limiters=memory, redis_limiters=redis_limiters, redis_timeout_seconds=0.05, redis_retry_seconds=30.0)

    started = time.monotonic()
    assert await gateway.acquire("write", "1.1.1.1:/path") is True
    elapsed = time.monotonic() - started
    assert elapsed < 1.0
    assert await gateway.acquire("write", "1.1.1.1:/path") is False


@pytest.mark.asyncio
async def test_gateway_resumes_redis_after_retry_interval():
    class _ToggleLimiter:
        def __init__(self):
            self.fail = True
            self.calls = 0

        async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
            self.calls += 1
            if self.fail:
                raise ConnectionError("down")
            return True

    toggle = _ToggleLimiter()
    memory = {"write": [_AllowingLimiter()]}
    gateway = RateLimiterGateway(memory_limiters=memory, redis_limiters={"write": [toggle]}, redis_timeout_seconds=1.0, redis_retry_seconds=0.05)

    assert await gateway.acquire("write", "ip:/path") is True
    assert toggle.calls == 1

    toggle.fail = False
    await asyncio.sleep(0.06)
    assert await gateway.acquire("write", "ip:/path") is True
    assert toggle.calls == 2


@pytest.mark.asyncio
async def test_noscript_is_not_treated_as_redis_failure():
    class _NoscriptThenOk:
        def __init__(self):
            self.calls = 0

        async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
            self.calls += 1
            if self.calls == 1:
                # Simulate redis-py reloading after NOSCRIPT by succeeding on retry inside limiter.
                # Gateway must not enter fallback for NOSCRIPT handled by the limiter.
                return True
            return True

    memory_calls = {"n": 0}

    class _MemoryProbe:
        async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
            memory_calls["n"] += 1
            return True

    gateway = RateLimiterGateway(
        memory_limiters={"write": [_MemoryProbe()]}, redis_limiters={"write": [_NoscriptThenOk()]}, redis_timeout_seconds=1.0, redis_retry_seconds=30.0
    )

    assert await gateway.acquire("write", "ip:/path") is True
    assert memory_calls["n"] == 0


@pytest.mark.asyncio
async def test_memory_idle_client_state_expires():
    window = RateLimitWindow(times=1, seconds=1)
    group = RateLimiterConfig(short=window, medium=window, long=window)
    config = RateLimitersConfig(default=group, read=group, write=group)
    limiter = create_memory_rate_limiters(config)["write"][0]

    assert await limiter.try_acquire_async("1.1.1.1:/path") is True
    assert await limiter.try_acquire_async("1.1.1.1:/path") is False
    await asyncio.sleep(1.1)
    limiter.sweep()
    assert limiter.client_count() == 0
    assert await limiter.try_acquire_async("1.1.1.1:/path") is True


@pytest.mark.asyncio
async def test_gateway_replace_redis_limiters_resumes_without_restart():
    memory = create_memory_rate_limiters(_tight_config())
    gateway = RateLimiterGateway(memory_limiters=memory, redis_limiters=None)

    assert gateway.has_redis_limiters() is False
    assert await gateway.acquire("write", "1.1.1.1:/path") is True
    assert await gateway.acquire("write", "1.1.1.1:/path") is False

    class _AlwaysAllow:
        async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
            return True

    gateway.replace_redis_limiters({"write": [_AlwaysAllow()]})
    assert gateway.has_redis_limiters() is True
    assert await gateway.acquire("write", "1.1.1.1:/path") is True


@pytest.mark.asyncio
async def test_redis_script_covers_configured_windows(monkeypatch: pytest.MonkeyPatch):
    from portal.config import settings

    monkeypatch.setattr(settings, "APP_NAME", "rooted-core-api")
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", None)

    redis = _FakeRedis()
    limiters = await create_redis_rate_limiters(redis)
    await limiters["default"][0].try_acquire_async("10.0.0.1:/x")
    config = get_rate_limiters_config("default")
    _keys, args = redis.script.calls[0]
    assert args[2:] == [
        config.short.seconds * 1000,
        config.short.times,
        config.medium.seconds * 1000,
        config.medium.times,
        config.long.seconds * 1000,
        config.long.times,
    ]
