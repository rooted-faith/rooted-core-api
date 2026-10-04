"""
Redis-backed ephemeral OTP store (hashed passcodes, TTL) and per-email request quota (ADR 0008).
"""

from redis.asyncio import Redis

from portal.config import settings
from portal.libs.consts.cache_keys import CacheKeys
from portal.libs.database import RedisPool

_CONSUME_LUA = """
local stored = redis.call('GET', KEYS[1])
if stored == false then
  return 0
end
if stored ~= ARGV[1] then
  return 0
end
redis.call('DEL', KEYS[1])
return 1
"""

_QUOTA_LUA = """
local used = redis.call('INCR', KEYS[1])
if used == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
if used > tonumber(ARGV[1]) then
  return 0
end
return 1
"""


class OtpTokenCache:
    """Store one outstanding passcode hash per email with Redis TTL, and cap requests per email."""

    def __init__(self, redis_client: RedisPool):
        self._redis: Redis = redis_client.create(db=settings.REDIS_DB)

    @staticmethod
    def _cache_key(email: str) -> str:
        return CacheKeys(resource="otp").add_attribute(email.strip().lower()).build()

    @staticmethod
    def _quota_key(email: str) -> str:
        return CacheKeys(resource="otp_quota").add_attribute(email.strip().lower()).build()

    async def store(self, email: str, code_hash: str, ttl_seconds: int) -> None:
        await self._redis.setex(self._cache_key(email), ttl_seconds, code_hash)

    async def consume(self, email: str, code_hash: str) -> bool:
        result = await self._redis.eval(_CONSUME_LUA, 1, self._cache_key(email), code_hash)
        return bool(result)

    async def allow_request(self, email: str, *, max_requests: int, window_seconds: int) -> bool:
        result = await self._redis.eval(_QUOTA_LUA, 1, self._quota_key(email), max_requests, window_seconds)
        return bool(result)

    async def invalidate(self, email: str) -> None:
        await self._redis.delete(self._cache_key(email))
