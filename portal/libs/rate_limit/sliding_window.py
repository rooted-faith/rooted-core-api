"""
Per-client sliding-window rate limiters (Redis and in-process).
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from time import time_ns
from uuid import uuid4

from redis.asyncio import Redis

from portal.libs.consts.cache_keys import CacheKeys
from portal.libs.rate_limit.config import RateLimiterConfig

# KEYS[1]: client key. ARGV: now_ms, member, then (interval_ms, limit) per window.
# Rejects without recording when any window is full; otherwise records the request,
# trims entries older than the longest window, and expires the key after it.
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local longest = 0
for i = 3, #ARGV, 2 do
    local interval = tonumber(ARGV[i])
    if redis.call('ZCOUNT', key, now - interval, now) >= tonumber(ARGV[i + 1]) then
        return 0
    end
    if interval > longest then
        longest = interval
    end
end
redis.call('ZADD', key, now, ARGV[2])
redis.call('ZREMRANGEBYSCORE', key, 0, now - longest)
redis.call('PEXPIRE', key, longest)
return 1
"""


class RedisSlidingWindowLimiter:
    """
    Per-client limiter for one config type; all windows are checked in one script call.
    redis-py reloads the script on NOSCRIPT (lost script cache after FLUSH/failover).
    """

    def __init__(self, redis: Redis, config_type: str, config: RateLimiterConfig):
        self._script = redis.register_script(SLIDING_WINDOW_SCRIPT)
        self._key_prefix = CacheKeys(resource="rate_limiter").add_attribute(config_type).build()
        self._windows = [value for window in (config.short, config.medium, config.long) for value in (window.seconds * 1000, window.times)]

    async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
        now_ms = time_ns() // 1_000_000
        allowed = await self._script(keys=[f"{self._key_prefix}:{name}"], args=[now_ms, f"{now_ms}:{uuid4().hex}", *self._windows])
        return bool(allowed)


class MemorySlidingWindowLimiter:
    """
    Per-client in-process sliding windows. Idle clients expire after the longest window.
    Cleanup is lazy on acquire plus a single shared background sweep; it does not spawn
    per-client timers.
    """

    def __init__(self, config: RateLimiterConfig):
        self._windows = [(window.seconds * 1000, window.times) for window in (config.short, config.medium, config.long)]
        self._longest_ms = max(interval for interval, _ in self._windows)
        self._events: dict[str, list[int]] = defaultdict(list)
        self._lock = Lock()

    def client_count(self) -> int:
        with self._lock:
            self._sweep_expired(now_ms=time_ns() // 1_000_000)
            return len(self._events)

    def sweep(self) -> None:
        """Drop idle clients. Safe to call from a single shared background task."""
        with self._lock:
            self._sweep_expired(now_ms=time_ns() // 1_000_000)

    async def try_acquire_async(self, name: str, blocking: bool = False) -> bool:
        now_ms = time_ns() // 1_000_000
        with self._lock:
            timestamps = self._events[name]
            cutoff = now_ms - self._longest_ms
            timestamps[:] = [stamp for stamp in timestamps if stamp >= cutoff]
            for interval_ms, limit in self._windows:
                window_cutoff = now_ms - interval_ms
                if sum(1 for stamp in timestamps if stamp >= window_cutoff) >= limit:
                    if not timestamps:
                        self._events.pop(name, None)
                    return False
            timestamps.append(now_ms)
            return True

    def _sweep_expired(self, now_ms: int) -> None:
        cutoff = now_ms - self._longest_ms
        empty_keys = []
        for key, timestamps in self._events.items():
            timestamps[:] = [stamp for stamp in timestamps if stamp >= cutoff]
            if not timestamps:
                empty_keys.append(key)
        for key in empty_keys:
            self._events.pop(key, None)
