"""
Rate limiter gateway: Redis primary with per-worker in-memory fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class SlidingWindowLimiterPort(Protocol):
    async def try_acquire_async(self, name: str, blocking: bool = False) -> bool: ...


class RateLimiterGateway:
    """
    Acquires against Redis-backed limiters when healthy; otherwise in-memory.
    Redis calls wait at most redis_timeout_seconds. After a failure, Redis is
    retried after redis_retry_seconds. NOSCRIPT handled inside Redis limiters
    is not treated as a Redis failure.
    """

    def __init__(
        self,
        *,
        memory_limiters: dict[str, list[SlidingWindowLimiterPort]],
        redis_limiters: dict[str, list[SlidingWindowLimiterPort]] | None = None,
        redis_timeout_seconds: float = 1.0,
        redis_retry_seconds: float = 30.0,
    ):
        self._memory_limiters = memory_limiters
        self._redis_limiters = redis_limiters
        self._redis_timeout_seconds = redis_timeout_seconds
        self._redis_retry_seconds = redis_retry_seconds
        self._redis_unhealthy_until: float = 0.0

    def replace_redis_limiters(self, redis_limiters: dict[str, list[SlidingWindowLimiterPort]] | None) -> None:
        """Attach or clear Redis limiters after startup reconnect."""
        self._redis_limiters = redis_limiters
        self._redis_unhealthy_until = 0.0

    def has_redis_limiters(self) -> bool:
        return self._redis_limiters is not None

    def sweep_memory(self) -> None:
        """Run idle cleanup on every in-memory limiter (one shared background caller)."""
        for limiters in self._memory_limiters.values():
            for limiter in limiters:
                sweep = getattr(limiter, "sweep", None)
                if callable(sweep):
                    sweep()

    async def acquire(self, config_type: str, identifier: str) -> bool:
        if self._should_use_redis():
            try:
                return await asyncio.wait_for(self._acquire_from(self._redis_limiters, config_type, identifier), timeout=self._redis_timeout_seconds)
            except Exception as error:  # noqa: BLE001 — fall back; do not 500 the request
                self._redis_unhealthy_until = time.monotonic() + self._redis_retry_seconds
                logger.error("Redis rate limiter unavailable; using in-memory fallback: %s", error)

        return await self._acquire_from(self._memory_limiters, config_type, identifier)

    def _should_use_redis(self) -> bool:
        if not self._redis_limiters:
            return False
        return time.monotonic() >= self._redis_unhealthy_until

    async def _acquire_from(self, limiters_by_type: dict[str, list[SlidingWindowLimiterPort]] | None, config_type: str, identifier: str) -> bool:
        if not limiters_by_type:
            return True
        for limiter in limiters_by_type.get(config_type, []):
            if not await limiter.try_acquire_async(identifier, blocking=False):
                return False
        return True
