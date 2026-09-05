"""
Redis-backed ephemeral magic-link token store (hashed tokens, TTL).
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


class MagicLinkTokenCache:
    """Store one outstanding magic-link hash per email with Redis TTL."""

    def __init__(self, redis_client: RedisPool):
        self._redis: Redis = redis_client.create(db=settings.REDIS_DB)

    @staticmethod
    def _cache_key(email: str) -> str:
        return CacheKeys(resource="magic_link").add_attribute(email.strip().lower()).build()

    async def store(self, email: str, token_hash: str, ttl_seconds: int) -> None:
        await self._redis.setex(self._cache_key(email), ttl_seconds, token_hash)

    async def consume(self, email: str, token_hash: str) -> bool:
        result = await self._redis.eval(_CONSUME_LUA, 1, self._cache_key(email), token_hash)
        return bool(result)
