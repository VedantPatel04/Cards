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

from django.conf import settings

# TODO: build one module-level client from settings.REDIS_URL
#   import redis
#   _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
_client = None


def cache_get(merchant_key: str) -> str | None:
    """
    Return the cached MCC code for a merchant key.

    Returns:
      - a code string on hit,
      - ""   if the merchant is cached as a known-unknown,
      - None on a miss OR on any Redis failure (fail open).
    """
    # TODO: GET f"merchant:{merchant_key}" inside try/except (RedisError -> None)
    raise NotImplementedError


def cache_set(merchant_key: str, mcc_code: str) -> None:
    """
    Cache an MCC code (or "" for known-unknown) with the configured TTL.
    Silently no-ops if Redis is unavailable (fail open).
    """
    # TODO: SET f"merchant:{merchant_key}" with ex=settings.MERCHANT_CACHE_TTL
    #       inside try/except (RedisError -> return)
    raise NotImplementedError
