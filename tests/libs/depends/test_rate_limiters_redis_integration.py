"""
Isolated Redis integration for per-client rate limiting, SCRIPT FLUSH, and idle expiry.
Skipped when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import from_url as redis_from_url

from portal.config import settings
from portal.libs.depends.rate_limiters import RedisRateLimiterDependency, create_redis_rate_limiters
from portal.libs.rate_limit.config import RateLimiterConfig, RateLimitersConfig, RateLimitWindow
from portal.libs.rate_limit.gateway import RateLimiterGateway
from portal.libs.utils.lifespan import lifespan

REDIS_IMAGE = "redis:7.4-alpine"
CONTAINER_PREFIX = "rooted-rate-limiter-int"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, check=False, timeout=10)
    except FileNotFoundError, subprocess.TimeoutExpired, OSError:
        return False
    return result.returncode == 0


async def _ping_redis(url: str) -> None:
    client = redis_from_url(url, encoding="utf-8", decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()


def _wait_for_redis(url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            asyncio.run(_ping_redis(url))
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
            time.sleep(0.2)
    raise TimeoutError(f"Redis at {url} not ready: {last_error}")


def _start_redis() -> tuple[str, str]:
    port = _free_port()
    name = f"{CONTAINER_PREFIX}-{uuid.uuid4().hex[:8]}"
    url = f"redis://127.0.0.1:{port}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:6379",
            REDIS_IMAGE,
            "redis-server",
            "--databases",
            "1",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        pytest.skip(f"Could not start Redis container: {run.stderr.strip()}")
    _wait_for_redis(url)
    return url, name


def _stop_redis(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available")
    url, name = _start_redis()
    try:
        yield url
    finally:
        _stop_redis(name)


def _tight_config() -> RateLimitersConfig:
    window = RateLimitWindow(times=1, seconds=60)
    group = RateLimiterConfig(short=window, medium=window, long=window)
    return RateLimitersConfig(default=group, read=group, write=group)


def _public_mounted_app() -> FastAPI:
    api = FastAPI()

    @api.get("/v1/probe", dependencies=[Depends(RedisRateLimiterDependency("write"))])
    async def api_probe():
        return {"ok": True}

    admin = FastAPI()

    @admin.get("/api/v1/probe", dependencies=[Depends(RedisRateLimiterDependency("default"))])
    async def admin_probe():
        return {"ok": True}

    public = FastAPI()
    public.mount("/api", api)
    public.mount("/admin", admin)
    return public


@pytest.mark.asyncio
async def test_mounted_api_and_admin_return_429_through_public_app(redis_url: str, monkeypatch: pytest.MonkeyPatch):
    prefix = f"rooted-rl-mount-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "REDIS_URL", redis_url)
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    monkeypatch.setattr(settings, "RATE_LIMITER_REDIS_DB", 0)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)

    app = _public_mounted_app()
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/probe")).status_code == 200
            assert (await client.get("/api/v1/probe")).status_code == 429
            assert (await client.get("/admin/api/v1/probe")).status_code == 200
            assert (await client.get("/admin/api/v1/probe")).status_code == 429


@pytest.mark.asyncio
async def test_one_client_exhausting_quota_does_not_affect_another(redis_url: str, monkeypatch: pytest.MonkeyPatch):
    prefix = f"rooted-rl-iso-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "REDIS_URL", redis_url)
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    monkeypatch.setattr(settings, "RATE_LIMITER_REDIS_DB", 0)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "True-Client-IP")

    app = _public_mounted_app()
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/probe", headers={"True-Client-IP": "198.51.100.1"})).status_code == 200
            assert (await client.get("/api/v1/probe", headers={"True-Client-IP": "198.51.100.1"})).status_code == 429
            assert (await client.get("/api/v1/probe", headers={"True-Client-IP": "198.51.100.2"})).status_code == 200


@pytest.mark.asyncio
async def test_script_flush_reloads_without_fallback(redis_url: str, monkeypatch: pytest.MonkeyPatch):
    prefix = f"rooted-rl-flush-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())

    redis = redis_from_url(redis_url, db=0, encoding="utf-8", decode_responses=True)
    memory_hits = {"n": 0}

    class _MemoryProbe:
        async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
            memory_hits["n"] += 1
            return True

    try:
        redis_limiters = await create_redis_rate_limiters(redis)
        gateway = RateLimiterGateway(
            memory_limiters={"write": [_MemoryProbe()]}, redis_limiters=redis_limiters, redis_timeout_seconds=1.0, redis_retry_seconds=30.0
        )
        assert await gateway.acquire("write", "10.0.0.1:/flush") is True
        await redis.script_flush()
        assert await gateway.acquire("write", "10.0.0.2:/flush") is True
        assert memory_hits["n"] == 0
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_redis_idle_client_key_expires(redis_url: str, monkeypatch: pytest.MonkeyPatch):
    prefix = f"rooted-rl-ttl-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    window = RateLimitWindow(times=1, seconds=1)
    group = RateLimiterConfig(short=window, medium=window, long=window)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", RateLimitersConfig(default=group, read=group, write=group))

    redis = redis_from_url(redis_url, db=0, encoding="utf-8", decode_responses=True)
    try:
        limiter = (await create_redis_rate_limiters(redis))["write"][0]
        assert await limiter.try_acquire_async("10.0.0.9:/ttl") is True
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:rate_limiter:*")]
        assert len(keys) == 1
        await asyncio.sleep(1.2)
        keys_after = [key async for key in redis.scan_iter(match=f"{prefix}:rate_limiter:*")]
        assert keys_after == []
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_lifespan_without_redis_still_limits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_config())
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)

    app = _public_mounted_app()
    async with lifespan(app):
        gateway = app.state.rate_limiter_gateway
        assert gateway.has_redis_limiters() is False
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/probe")).status_code == 200
            assert (await client.get("/api/v1/probe")).status_code == 429
