"""
Rate limiters dependencies for API endpoints.

Rate limiters strategy:
1. Short-term rate limiting (1 second): Prevent sudden traffic, protect system stability
2. Medium-term rate limiting (30 seconds): Smooth traffic, avoid too many requests in a short period of time
3. Long-term rate limiting (1 hour): Total control, prevent long-term abuse

Different endpoint types rate limiters strategy:
- Read endpoint: Looser, because read operations are less burdened on the system
- Write endpoint: Stricter, because write operations need more resources

Limiters keep one sliding-window key per client identifier (resolved client IP + path).
When REDIS_URL is set, Redis is primary and shared across workers; on Redis failure the
gateway falls back to per-worker in-memory limiters. Lifespan attaches the gateway to
the public app and every mounted sub-app (request.app is the sub-app inside mounts).

Configuration file location: env/rate_limiters.yaml
"""

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from redis.asyncio import Redis
from starlette.routing import Mount

from portal.config import settings
from portal.libs.client_ip import resolved_client_ip
from portal.libs.rate_limit.config import RateLimiterConfig, RateLimitersConfig
from portal.libs.rate_limit.gateway import RateLimiterGateway
from portal.libs.rate_limit.sliding_window import MemorySlidingWindowLimiter, RedisSlidingWindowLimiter


async def default_identifier(request: Request) -> str:
    """
    Identifier for rate limit key: resolved client IP + path.
    Requests without a usable address share "unknown".
    """
    client_ip = resolved_client_ip(request, trusted_header=settings.TRUSTED_CLIENT_IP_HEADER)
    return f"{client_ip or 'unknown'}:{request.scope['path']}"


def get_rate_limiters_config(config_type: str = "default") -> RateLimiterConfig:
    """
    Get rate limiter config from configuration file

    :param config_type: Configuration type (default, read, write, admin)
    :return:
    """
    if not settings.RATE_LIMITERS_CONFIG:
        from portal.libs.rate_limit.config import RateLimitWindow

        return RateLimiterConfig(
            short=RateLimitWindow(times=3, seconds=1), medium=RateLimitWindow(times=20, seconds=30), long=RateLimitWindow(times=400, seconds=3600)
        )

    config_map = {"default": settings.RATE_LIMITERS_CONFIG.default, "read": settings.RATE_LIMITERS_CONFIG.read, "write": settings.RATE_LIMITERS_CONFIG.write}
    return config_map.get(config_type, settings.RATE_LIMITERS_CONFIG.default)


def create_memory_rate_limiters(full_config: RateLimitersConfig | None = None) -> dict[str, list[MemorySlidingWindowLimiter]]:
    """
    Create per-process in-memory limiters for default, read, and write.

    :param full_config: optional full config; otherwise settings / built-in defaults
    :return: Dict mapping config_type to its limiters
    """
    result: dict[str, list[MemorySlidingWindowLimiter]] = {}
    for config_type in ("default", "read", "write"):
        config = getattr(full_config, config_type) if full_config is not None else get_rate_limiters_config(config_type)
        result[config_type] = [MemorySlidingWindowLimiter(config)]
    return result


async def create_redis_rate_limiters(redis: Redis) -> dict[str, list[RedisSlidingWindowLimiter]]:
    """
    Create Redis-backed limiters for default, read, and write config types.

    :param redis: Async Redis client (redis.asyncio.Redis)
    :return: Dict mapping config_type to its limiters
    """
    return {config_type: [RedisSlidingWindowLimiter(redis, config_type, get_rate_limiters_config(config_type))] for config_type in ("default", "read", "write")}


def attach_rate_limiters(app: FastAPI, gateway: RateLimiterGateway | None) -> None:
    """
    Set the rate limiter gateway on the app and every mounted FastAPI sub-app.
    Inside a mounted app, request.app is the sub-app, so the root app's state alone is not visible there.
    """
    app.state.rate_limiter_gateway = gateway
    for route in app.routes:
        if isinstance(route, Mount) and isinstance(route.app, FastAPI):
            attach_rate_limiters(route.app, gateway)


class RedisRateLimiterDependency:
    """
    FastAPI dependency that applies rate limiters for a config type via the attached gateway.
    """

    def __init__(self, config_type: str):
        self.config_type = config_type

    async def __call__(self, request: Request) -> None:
        gateway: RateLimiterGateway | None = getattr(request.app.state, "rate_limiter_gateway", None)
        if gateway is None:
            return
        identifier = await default_identifier(request)
        if not await gateway.acquire(self.config_type, identifier):
            raise HTTPException(status_code=429, detail="Too Many Requests")


# Default rate limiter (for general endpoints)
DEFAULT_RATE_LIMITERS = [Depends(RedisRateLimiterDependency("default"))]
# Read endpoint rate limiter (looser)
READ_RATE_LIMITERS = [Depends(RedisRateLimiterDependency("read"))]
# Write endpoint rate limiter (stricter)
WRITE_RATE_LIMITERS = [Depends(RedisRateLimiterDependency("write"))]
