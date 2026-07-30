from redis.asyncio import Redis

from fastapi import HTTPException, status

from app.core.config import (
    ORDER_RATE_LIMIT,
    ORDER_RATE_WINDOW_SECONDS,
    REDIS_URL,
)

_redis: Redis | None = None


async def connect_redis() -> None:
    global _redis
    _redis = Redis.from_url(REDIS_URL, decode_responses=True)


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis is not initialized")
    return _redis


async def enforce_order_rate_limit(user_id: str) -> None:
    """
    Fixed-window limit: max ORDER_RATE_LIMIT place-order calls
    per user per ORDER_RATE_WINDOW_SECONDS.
    """
    redis = get_redis()
    key = f"rate:orders:{user_id}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, ORDER_RATE_WINDOW_SECONDS)

    if count > ORDER_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: max {ORDER_RATE_LIMIT} orders "
                f"per {ORDER_RATE_WINDOW_SECONDS}s. Try again later."
            ),
            headers={"Retry-After": str(ORDER_RATE_WINDOW_SECONDS)},
        )