"""
App support policy read from system settings (namespace `app_support`, one `object` setting per platform).

Read path per call (docs/operations/app-support-policy.md):
1. Redis GET of the setting key. A hit is used as is.
2. On a miss, read the row from the database with a short-lived session of its own (the gate runs
   outside the request session) and cache a found value for CACHE_TTL_SECONDS.
3. On a Redis error or a Redis read slower than CACHE_TIMEOUT_SECONDS, read the database without caching.
4. On a database error or a read slower than DATABASE_TIMEOUT_SECONDS, use this process's last successful read if it is at most
   LAST_KNOWN_GOOD_MAX_AGE_SECONDS old; otherwise the platform is unavailable (fail closed).

An admin save invalidates the key, so the next read after the save loads the new row.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

import asyncpg
from redis.exceptions import RedisError

from portal.domain.app_support.constants import APP_SUPPORT_SETTING_NAMESPACE, AppPlatform
from portal.domain.app_support.entities import AppSupportPolicy
from portal.domain.app_support.policy import InvalidAppSupportPolicy, parse_platform_policy
from portal.domain.system.entities import Setting
from portal.infrastructure.persistence.repositories.system.setting_repository import SettingRepository
from portal.libs.database import Session
from portal.libs.logger import logger

# Bounds how long a value cached by a read that raced an admin save (before its commit) can outlive the save.
CACHE_TTL_SECONDS = 60
# How long this process keeps answering from its last successful read while Redis and the database both fail.
LAST_KNOWN_GOOD_MAX_AGE_SECONDS = 300
# The Redis client and the database session have no read timeout of their own; a hung backend must not hang the gate.
CACHE_TIMEOUT_SECONDS = 0.5
DATABASE_TIMEOUT_SECONDS = 2.0

# TimeoutError (from asyncio.timeout) is an OSError; ValueError covers a cached value that is not valid JSON.
_REDIS_ERRORS = (RedisError, OSError, ValueError)
_DATABASE_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError)

LoadSetting = Callable[[str, str], Awaitable[Setting | None]]


class _SettingCachePort(Protocol):
    async def lookup(self, namespace: str, setting_key: str) -> tuple[bool, Any]: ...

    async def set_value(self, namespace: str, setting_key: str, value: Any, ex: int = ...) -> None: ...


class _Unreadable(Exception):
    """Neither Redis nor the database answered."""


@dataclass(frozen=True)
class _Snapshot:
    policy: AppSupportPolicy | None
    read_at: float


class SessionSettingLoader:
    """Read one setting row with its own database session, closed before returning."""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    async def __call__(self, namespace: str, setting_key: str) -> Setting | None:
        session = self._session_factory()
        try:
            return await SettingRepository(session).get_by_namespace_key(namespace, setting_key)
        finally:
            await session.close()


class SettingAppSupportPolicySource:
    """Each platform is read and validated on its own, so one broken setting leaves the other platform usable."""

    def __init__(
        self,
        environment: str,
        setting_cache: _SettingCachePort,
        load_setting: LoadSetting,
        clock: Callable[[], float] = time.monotonic,
        cache_timeout: float = CACHE_TIMEOUT_SECONDS,
        database_timeout: float = DATABASE_TIMEOUT_SECONDS,
    ):
        self._environment = environment.lower()
        self._cache = setting_cache
        self._load_setting = load_setting
        self._clock = clock
        self._cache_timeout = cache_timeout
        self._database_timeout = database_timeout
        self._last_known_good: dict[AppPlatform, _Snapshot] = {}

    @property
    def environment(self) -> str:
        return self._environment

    async def get(self, platform: AppPlatform) -> AppSupportPolicy | None:
        try:
            value = await self._read_value(platform)
        except _Unreadable:
            return self._fallback(platform)
        policy = self._parse(platform, value)
        self._last_known_good[platform] = _Snapshot(policy=policy, read_at=self._clock())
        return policy

    async def _read_value(self, platform: AppPlatform) -> Any:
        key = platform.value
        cache_usable = True
        try:
            async with asyncio.timeout(self._cache_timeout):
                hit, value = await self._cache.lookup(APP_SUPPORT_SETTING_NAMESPACE, key)
            if hit:
                return value
        except _REDIS_ERRORS as exc:
            cache_usable = False
            logger.warning(f"App support policy cache read failed for {key}; reading the database: {exc!r}")

        try:
            async with asyncio.timeout(self._database_timeout):
                row = await self._load_setting(APP_SUPPORT_SETTING_NAMESPACE, key)
        except _DATABASE_ERRORS as exc:
            logger.error(f"App support policy database read failed for {key}: {exc!r}")
            raise _Unreadable from exc

        value = row.value if row is not None and row.is_active else None
        if value is not None and cache_usable:
            try:
                async with asyncio.timeout(self._cache_timeout):
                    await self._cache.set_value(APP_SUPPORT_SETTING_NAMESPACE, key, value, ex=CACHE_TTL_SECONDS)
            except _REDIS_ERRORS as exc:
                logger.warning(f"App support policy cache write failed for {key}: {exc!r}")
        return value

    def _parse(self, platform: AppPlatform, value: Any) -> AppSupportPolicy | None:
        # Log when a platform becomes unavailable, not on every request while it stays so.
        previous = self._last_known_good.get(platform)
        changed = previous is None or previous.policy is not None
        if value is None:
            if changed:
                logger.warning(f"System setting {APP_SUPPORT_SETTING_NAMESPACE}.{platform.value} is missing or inactive; that platform's policy is unavailable")
            return None
        try:
            return parse_platform_policy(platform, value)
        except InvalidAppSupportPolicy as exc:
            if changed:
                logger.error(f"System setting {APP_SUPPORT_SETTING_NAMESPACE}.{platform.value} is invalid and unavailable: {exc}")
            return None

    def _fallback(self, platform: AppPlatform) -> AppSupportPolicy | None:
        snapshot = self._last_known_good.get(platform)
        if snapshot is None or self._clock() - snapshot.read_at > LAST_KNOWN_GOOD_MAX_AGE_SECONDS:
            return None
        return snapshot.policy
