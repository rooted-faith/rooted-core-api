"""
Util functions for lifespan
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import from_url as redis_from_url

from portal.config import settings
from portal.container import Container
from portal.libs.depends.rate_limiters import attach_rate_limiters, create_memory_rate_limiters, create_redis_rate_limiters
from portal.libs.logger import logger
from portal.libs.rate_limit.gateway import RateLimiterGateway

REDIS_RETRY_SECONDS = 30.0
MEMORY_SWEEP_SECONDS = 5.0


async def _connect_rate_limiter_redis():
    """
    Open a Redis client for rate limiting and build limiters.
    :return: (redis_connection, redis_limiters)
    """
    redis_connection = redis_from_url(settings.REDIS_URL, db=settings.RATE_LIMITER_REDIS_DB, encoding="utf-8", decode_responses=True)
    await redis_connection.ping()
    redis_limiters = await create_redis_rate_limiters(redis_connection)
    return redis_connection, redis_limiters


async def _redis_reconnect_loop(gateway: RateLimiterGateway, redis_holder: dict) -> None:
    """
    When Redis was unavailable at startup (or dropped later with no limiters attached),
    retry every REDIS_RETRY_SECONDS and switch back without a process restart.
    """
    while True:
        await asyncio.sleep(REDIS_RETRY_SECONDS)
        if gateway.has_redis_limiters():
            continue
        if not settings.REDIS_URL:
            continue
        try:
            redis_connection, redis_limiters = await _connect_rate_limiter_redis()
            previous = redis_holder.get("connection")
            redis_holder["connection"] = redis_connection
            gateway.replace_redis_limiters(redis_limiters)
            logger.info("Redis rate limiters reconnected")
            if previous is not None:
                try:
                    await previous.aclose()
                except Exception as close_error:
                    logger.warning("Failed to close previous Redis rate limiter connection: %s", close_error)
        except Exception as error:
            logger.error("Redis rate limiter reconnect failed; staying on in-memory fallback: %s", error)


async def _memory_sweep_loop(gateway: RateLimiterGateway) -> None:
    """Single shared idle-cleanup task; does not grow with client count."""
    while True:
        await asyncio.sleep(MEMORY_SWEEP_SECONDS)
        gateway.sweep_memory()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan
    :param app:
    """
    logger.info("Starting lifespan")
    # Register event handlers (optional - add Container.register_event_handlers in your project)
    if hasattr(app, "container"):
        try:
            container = app.container
            event_bus = container.event_bus()
            logger.info("-" * 100)
            Container.register_event_handlers(event_bus, container)
            logger.info("Event handlers registered")
            logger.info("-" * 100)
        except Exception as e:
            logger.warning("Failed to register event handlers: %s", e)

    otp_test_policy_watch = None
    if hasattr(app, "container"):
        try:
            otp_test_policy_watch = asyncio.create_task(app.container.app.otp_test_passcode_service().watch())
        except Exception as e:
            logger.warning("Failed to start watching the test passcode policy: %s", type(e).__name__)

    redis_holder: dict = {"connection": None}
    memory_limiters = create_memory_rate_limiters()
    redis_limiters = None
    if settings.REDIS_URL:
        try:
            redis_holder["connection"], redis_limiters = await _connect_rate_limiter_redis()
            logger.info("Redis rate limiters initialized")
        except Exception as e:
            logger.error("Failed to initialize Redis rate limiters; using in-memory fallback: %s", e)
            if redis_holder["connection"] is not None:
                try:
                    await redis_holder["connection"].aclose()
                except Exception as close_error:
                    logger.warning("Failed to close Redis rate limiter connection after init error: %s", close_error)
                redis_holder["connection"] = None

    gateway = RateLimiterGateway(memory_limiters=memory_limiters, redis_limiters=redis_limiters)
    attach_rate_limiters(app, gateway)

    redis_reconnect_task = None
    memory_sweep_task = asyncio.create_task(_memory_sweep_loop(gateway))
    if settings.REDIS_URL:
        redis_reconnect_task = asyncio.create_task(_redis_reconnect_loop(gateway, redis_holder))

    yield

    if otp_test_policy_watch is not None:
        otp_test_policy_watch.cancel()
    memory_sweep_task.cancel()
    if redis_reconnect_task is not None:
        redis_reconnect_task.cancel()

    if redis_holder["connection"] is not None:
        try:
            await redis_holder["connection"].aclose()
        except Exception as e:
            logger.warning("Failed to close Redis rate limiter connection: %s", e)

    logger.info("Lifespan finished")
