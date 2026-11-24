"""
Redis-backed ephemeral passcode challenges (hashed, TTL) and per-email request quota (ADR 0008, ADR 0016).
"""

import time
from typing import Optional

from redis.asyncio import Redis

from portal.config import settings
from portal.domain.auth.constants import OtpDeliveryMode
from portal.domain.auth.entities import OtpChallenge
from portal.libs.consts.cache_keys import CacheKeys
from portal.libs.database import RedisPool

# Emailed challenges keep the bare-hash form used before challenge origin existed, so a deploy does not drop them.
_FIXED_PREFIX = "fixed:"
# Tolerates clock skew between instances when pruning index entries of expired challenges.
_INDEX_PRUNE_GRACE_SECONDS = 3600

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
    """Store one outstanding challenge per email with Redis TTL, and cap requests per email."""

    def __init__(self, redis_client: RedisPool):
        self._redis: Redis = redis_client.create(db=settings.REDIS_DB)

    @staticmethod
    def _cache_key(email: str) -> str:
        return CacheKeys(resource="otp").add_attribute(email.strip().lower()).build()

    @staticmethod
    def _quota_key(email: str) -> str:
        return CacheKeys(resource="otp_quota").add_attribute(email.strip().lower()).build()

    @staticmethod
    def _fixed_index_key() -> str:
        return CacheKeys(resource="otp_fixed_index").build()

    @staticmethod
    def _encode(challenge: OtpChallenge) -> str:
        return f"{_FIXED_PREFIX}{challenge.code_hash}" if challenge.delivery_mode is OtpDeliveryMode.FIXED else challenge.code_hash

    @staticmethod
    def _decode(value: str) -> OtpChallenge:
        if value.startswith(_FIXED_PREFIX):
            return OtpChallenge(delivery_mode=OtpDeliveryMode.FIXED, code_hash=value.removeprefix(_FIXED_PREFIX))
        return OtpChallenge(delivery_mode=OtpDeliveryMode.EMAIL, code_hash=value)

    async def store(self, email: str, challenge: OtpChallenge, ttl_seconds: int) -> None:
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.set(self._cache_key(email), self._encode(challenge), ex=ttl_seconds)
            if challenge.delivery_mode is OtpDeliveryMode.FIXED:
                pipeline.zadd(self._fixed_index_key(), {email.strip().lower(): time.time() + ttl_seconds})
                pipeline.expire(self._fixed_index_key(), ttl_seconds + _INDEX_PRUNE_GRACE_SECONDS)
            await pipeline.execute()

    async def get(self, email: str) -> Optional[OtpChallenge]:
        value = await self._redis.get(self._cache_key(email))
        return None if value is None else self._decode(value)

    async def consume(self, email: str, challenge: OtpChallenge) -> bool:
        result = await self._redis.eval(_CONSUME_LUA, 1, self._cache_key(email), self._encode(challenge))
        return bool(result)

    async def list_fixed(self) -> list[tuple[str, OtpChallenge]]:
        index_key = self._fixed_index_key()
        await self._redis.zremrangebyscore(index_key, "-inf", time.time() - _INDEX_PRUNE_GRACE_SECONDS)
        emails = await self._redis.zrange(index_key, 0, -1)
        if not emails:
            return []
        values = await self._redis.mget([self._cache_key(email) for email in emails])
        challenges = [(email, self._decode(value)) for email, value in zip(emails, values) if value is not None]
        return [(email, challenge) for email, challenge in challenges if challenge.delivery_mode is OtpDeliveryMode.FIXED]

    async def allow_request(self, email: str, *, max_requests: int, window_seconds: int) -> bool:
        result = await self._redis.eval(_QUOTA_LUA, 1, self._quota_key(email), max_requests, window_seconds)
        return bool(result)
