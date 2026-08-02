"""
Phase 4 — Redis exact-match cache (cache-aside, fails open).

Thin wrapper around a single Redis client. Keys are namespaced as
"merchant:{merchant_key}". Every call is wrapped so that if Redis is
unreachable the pipeline keeps working (get -> None, set -> no-op).

Design decisions to implement:
  - Key namespace:  f"merchant:{merchant_key}"
  - TTL:            settings.MERCHANT_CACHE_TTL (seconds) on every set
  - Fail open:      catch redis errors; never raise into the resolver
  - Sentinel:       store "" to represent a cached "known-unknown" so we do
                    not re-hit the LLM for a merchant it already failed on
"""
import redis
from django.conf import settings



redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
)


def cache_get(merchant_key: str) -> str | None:
    """
    Return the cached MCC code for a merchant key.

    Returns:
      - a code string on hit,
      - ""   if the merchant is cached as a known-unknown,
      - None on a miss OR on any Redis failure (fail open).
    """
    try:
        return redis_client.get(f"merchant:{merchant_key}")
    except redis.RedisError:
        return None


def cache_set(merchant_key: str, mcc_code: str) -> None:
    """
    Cache an MCC code (or "" for known-unknown) with the configured TTL.
    Silently no-ops if Redis is unavailable (fail open).
    """
    try:
        redis_client.set(f"merchant:{merchant_key}", mcc_code, ex=settings.MERCHANT_CACHE_TTL)
    except redis.RedisError:
        return
