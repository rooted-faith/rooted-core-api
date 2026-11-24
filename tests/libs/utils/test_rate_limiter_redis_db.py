"""
Regression: rate limiter lifespan against a single-logical-DB Redis.

Starts an ephemeral Redis with ``databases 1`` so DB index 10 cannot work.
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
from fastapi import FastAPI, HTTPException
from redis.asyncio import from_url as redis_from_url
from starlette.requests import Request

from portal.config import settings
from portal.libs.depends.rate_limiters import RedisRateLimiterDependency
from portal.libs.rate_limit.config import RateLimiterConfig, RateLimitersConfig, RateLimitWindow
from portal.libs.rate_limit.gateway import RateLimiterGateway
from portal.libs.utils.lifespan import lifespan

REDIS_IMAGE = "redis:7.4-alpine"
CONTAINER_PREFIX = "rooted-rate-limiter-db-test"


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
        except Exception as error:  # noqa: BLE001 — probe until ready or timeout
            last_error = error
            time.sleep(0.2)
    raise TimeoutError(f"Redis at {url} not ready: {last_error}")


def _start_redis(*, databases: int) -> tuple[str, str]:
    port = _free_port()
    name = f"{CONTAINER_PREFIX}-{databases}db-{uuid.uuid4().hex[:8]}"
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
            str(databases),
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
def single_db_redis_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available")
    url, name = _start_redis(databases=1)
    try:
        yield url
    finally:
        _stop_redis(name)


@pytest.fixture(scope="module")
def multi_db_redis_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available")
    url, name = _start_redis(databases=16)
    try:
        yield url
    finally:
        _stop_redis(name)


def _tight_limiters_config() -> RateLimitersConfig:
    window = RateLimitWindow(times=1, seconds=60)
    group = RateLimiterConfig(short=window, medium=window, long=window)
    return RateLimitersConfig(default=group, read=group, write=group)


def _mock_request(app: FastAPI, path: str = "/rate-limit-probe") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("203.0.113.10", 12345),
        "server": ("test", 80),
        "app": app,
    }
    return Request(scope)


async def _cleanup_limiter_keys(url: str, prefix: str, db: int = 0) -> None:
    client = redis_from_url(url, db=db, encoding="utf-8", decode_responses=True)
    try:
        keys = [key async for key in client.scan_iter(match=f"{prefix}:rate_limiter*")]
        if keys:
            await client.delete(*keys)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_lifespan_initializes_limiters_on_single_db_redis_with_default_db(single_db_redis_url: str, monkeypatch: pytest.MonkeyPatch):
    """
    Path-free REDIS_URL and RATE_LIMITER_REDIS_DB=0 (Configuration default)
    must initialize against Redis with databases=1.
    """
    prefix = f"rooted-rl-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "REDIS_URL", single_db_redis_url)
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_limiters_config())
    monkeypatch.setattr(settings, "RATE_LIMITER_REDIS_DB", 0)
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)

    app = FastAPI()
    async with lifespan(app):
        gateway = getattr(app.state, "rate_limiter_gateway", None)
        assert isinstance(gateway, RateLimiterGateway)
        assert gateway.has_redis_limiters() is True

        for config_type in ("default", "read", "write"):
            dependency = RedisRateLimiterDependency(config_type)
            request = _mock_request(app, path=f"/probe/{config_type}")
            await dependency(request)
            with pytest.raises(HTTPException) as raised:
                await dependency(request)
            assert raised.value.status_code == 429

    await _cleanup_limiter_keys(single_db_redis_url, prefix)


@pytest.mark.asyncio
async def test_lifespan_falls_back_to_memory_when_rate_limiter_db_out_of_range(single_db_redis_url: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "REDIS_URL", single_db_redis_url)
    monkeypatch.setattr(settings, "APP_NAME", f"rooted-rl-bad-{uuid.uuid4().hex}")
    monkeypatch.setattr(settings, "RATE_LIMITER_REDIS_DB", 10)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_limiters_config())
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)

    app = FastAPI()
    async with lifespan(app):
        gateway = app.state.rate_limiter_gateway
        assert isinstance(gateway, RateLimiterGateway)
        assert gateway.has_redis_limiters() is False
        dependency = RedisRateLimiterDependency("default")
        request = _mock_request(app)
        await dependency(request)
        with pytest.raises(HTTPException) as raised:
            await dependency(request)
        assert raised.value.status_code == 429


@pytest.mark.asyncio
async def test_explicit_rate_limiter_db_override_works(multi_db_redis_url: str, monkeypatch: pytest.MonkeyPatch):
    prefix = f"rooted-rl-ovr-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "REDIS_URL", multi_db_redis_url)
    monkeypatch.setattr(settings, "APP_NAME", prefix)
    monkeypatch.setattr(settings, "RATE_LIMITER_REDIS_DB", 1)
    monkeypatch.setattr(settings, "RATE_LIMITERS_CONFIG", _tight_limiters_config())
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", None)

    app = FastAPI()
    async with lifespan(app):
        dependency = RedisRateLimiterDependency("default")
        request = _mock_request(app)
        await dependency(request)
        with pytest.raises(HTTPException) as raised:
            await dependency(request)
        assert raised.value.status_code == 429

    await _cleanup_limiter_keys(multi_db_redis_url, prefix, db=1)
