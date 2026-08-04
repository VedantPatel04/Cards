"""
Redis cache for a user's merchant -> rewards category answers (fails open).

Keys are namespaced per user as "merchant:{user_id}:{merchant_key}". The user
id is part of the key on purpose: a shared namespace would serve one user's
label to everyone else.

Every call is wrapped so that if Redis is unreachable the pipeline keeps
working (get -> None, set -> no-op). Redis is CACHE ONLY.
"""

import redis
from django.conf import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
)


def _key(user_id: int, merchant_key: str) -> str:
    return f"merchant:{user_id}:{merchant_key}"


def cache_get(user_id: int, merchant_key: str) -> str | None:
    """
    Return this user's cached category for a merchant key.

    Returns the category string on a hit, or None on a miss OR on any Redis
    failure (fail open).
    """
    try:
        return redis_client.get(_key(user_id, merchant_key))
    except redis.RedisError:
        return None


def cache_set(user_id: int, merchant_key: str, category: str) -> None:
    """Cache a category with the configured TTL. No-ops if Redis is down."""
    try:
        redis_client.set(
            _key(user_id, merchant_key),
            category,
            ex=settings.MERCHANT_CACHE_TTL,
        )
    except redis.RedisError:
        return


def cache_delete(user_id: int, merchant_key: str) -> None:
    """Drop a cached answer so the next resolve re-reads the DB."""
    try:
        redis_client.delete(_key(user_id, merchant_key))
    except redis.RedisError:
        return
