"""Real adapters behind the App support policy source (ROO-171): the database loader and the cache lookup."""

import asyncio

import pytest

from portal.infrastructure.app_support import setting_policy_source
from portal.infrastructure.app_support.setting_policy_source import SessionSettingLoader
from portal.infrastructure.cache.setting_cache import SettingCache


class _FakeSession:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


class _FakeRepository:
    behaviour = "return"

    def __init__(self, session) -> None:
        self.session = session

    async def get_by_namespace_key(self, namespace: str, setting_key: str):
        if self.behaviour == "raise":
            raise ConnectionRefusedError("database is unavailable")
        if self.behaviour == "hang":
            await asyncio.sleep(60)
        return (namespace, setting_key)


@pytest.fixture
def session(monkeypatch) -> _FakeSession:
    monkeypatch.setattr(setting_policy_source, "SettingRepository", _FakeRepository)
    return _FakeSession()


@pytest.mark.asyncio
@pytest.mark.parametrize("behaviour", ["return", "raise", "hang"])
async def test_the_loader_always_closes_its_own_session(session, behaviour, monkeypatch):
    monkeypatch.setattr(_FakeRepository, "behaviour", behaviour)
    loader = SessionSettingLoader(session_factory=lambda: session)

    if behaviour == "return":
        assert await loader("app_support", "ios") == ("app_support", "ios")
    elif behaviour == "raise":
        with pytest.raises(ConnectionRefusedError):
            await loader("app_support", "ios")
    else:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await loader("app_support", "ios")

    assert session.closed == 1


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ex: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value
        self.ex[key] = ex


class _FakeRedisPool:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis

    def create(self, db: int = 0) -> _FakeRedis:
        return self._redis


@pytest.mark.asyncio
async def test_cache_lookup_tells_a_missing_key_from_a_cached_value_and_honours_the_ttl():
    redis = _FakeRedis()
    cache = SettingCache(redis_client=_FakeRedisPool(redis))

    missing = await cache.lookup("app_support", "ios")
    await cache.set_value("app_support", "ios", {"minimum_build": 1}, ex=60)
    hit = await cache.lookup("app_support", "ios")

    assert missing == (False, None)
    assert hit == (True, {"minimum_build": 1})
    assert list(redis.ex.values()) == [60]
