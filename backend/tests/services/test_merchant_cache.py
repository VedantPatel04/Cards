"""
merchant_cache tests.

Strategy: mock the module-level _client so tests never need a real Redis
server. This lets us verify all behaviour — hits, misses, sentinel, TTL,
fail-open — without any network dependency.
"""

from unittest.mock import MagicMock, patch

import redis
from django.test import SimpleTestCase, override_settings

import services.merchant_cache as cache_module
from services.merchant_cache import cache_get, cache_set


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(get_return=None):
    """Return a mock Redis client whose .get() returns get_return."""
    client = MagicMock()
    client.get.return_value = get_return
    return client


# ---------------------------------------------------------------------------
# cache_get — happy path
# ---------------------------------------------------------------------------

class CacheGetHitTests(SimpleTestCase):
    def test_returns_mcc_on_hit(self):
        with patch.object(cache_module, "redis_client", _make_client("5814")):
            self.assertEqual(cache_get("MCDONALDS"), "5814")

    def test_uses_namespaced_key(self):
        """Key sent to Redis must be prefixed with 'merchant:'."""
        client = _make_client("5814")
        with patch.object(cache_module, "redis_client", client):
            cache_get("MCDONALDS")
        client.get.assert_called_once_with("merchant:MCDONALDS")

    def test_returns_sentinel_empty_string_on_known_unknown(self):
        """'' means 'we already tried and failed' — distinct from None (miss)."""
        with patch.object(cache_module, "redis_client", _make_client("")):
            result = cache_get("TOTALLY UNKNOWN")
        self.assertEqual(result, "")

    def test_returns_none_on_cache_miss(self):
        with patch.object(cache_module, "redis_client", _make_client(None)):
            self.assertIsNone(cache_get("UNKNOWN MERCHANT"))


# ---------------------------------------------------------------------------
# cache_get — fail open
# ---------------------------------------------------------------------------

class CacheGetFailOpenTests(SimpleTestCase):
    def _patched_client_that_raises(self, exc):
        client = MagicMock()
        client.get.side_effect = exc
        return client

    def test_connection_error_returns_none(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.ConnectionError)):
            self.assertIsNone(cache_get("MCDONALDS"))

    def test_timeout_error_returns_none(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.TimeoutError)):
            self.assertIsNone(cache_get("MCDONALDS"))

    def test_generic_redis_error_returns_none(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.RedisError)):
            self.assertIsNone(cache_get("MCDONALDS"))

    def test_does_not_raise_on_redis_error(self):
        """Caller must never see a RedisError bubble up."""
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.RedisError)):
            try:
                cache_get("ANY KEY")
            except redis.RedisError:
                self.fail("cache_get raised RedisError — must fail open")

    def test_return_type_is_str_or_none(self):
        for side_effect, expected_type in [
            (None, type(None)),     # miss
            ("5814", str),          # hit
            ("", str),              # sentinel
        ]:
            client = _make_client(side_effect)
            with patch.object(cache_module, "redis_client", client):
                result = cache_get("MCDONALDS")
            with self.subTest(side_effect=side_effect):
                self.assertIsInstance(result, expected_type)


# ---------------------------------------------------------------------------
# cache_set — happy path
# ---------------------------------------------------------------------------

class CacheSetTests(SimpleTestCase):
    def test_stores_mcc_under_namespaced_key(self):
        client = _make_client()
        with patch.object(cache_module, "redis_client", client):
            cache_set("MCDONALDS", "5814")
        client.set.assert_called_once()
        args, kwargs = client.set.call_args
        self.assertEqual(args[0], "merchant:MCDONALDS")
        self.assertEqual(args[1], "5814")

    def test_uses_configured_ttl(self):
        client = _make_client()
        with override_settings(MERCHANT_CACHE_TTL=3600):
            with patch.object(cache_module, "redis_client", client):
                cache_set("WAL MART", "5411")
        _, kwargs = client.set.call_args
        self.assertEqual(kwargs.get("ex"), 3600)

    def test_stores_sentinel_empty_string(self):
        """Cache '' to prevent re-hitting LLM for a known-unknown merchant."""
        client = _make_client()
        with patch.object(cache_module, "redis_client", client):
            cache_set("MYSTERY MERCHANT", "")
        args, _ = client.set.call_args
        self.assertEqual(args[1], "")

    def test_returns_none(self):
        client = _make_client()
        with patch.object(cache_module, "redis_client", client):
            result = cache_set("MCDONALDS", "5814")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# cache_set — fail open
# ---------------------------------------------------------------------------

class CacheSetFailOpenTests(SimpleTestCase):
    def _patched_client_that_raises(self, exc):
        client = MagicMock()
        client.set.side_effect = exc
        return client

    def test_connection_error_silently_noops(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.ConnectionError)):
            cache_set("MCDONALDS", "5814")  # must not raise

    def test_timeout_error_silently_noops(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.TimeoutError)):
            cache_set("MCDONALDS", "5814")

    def test_generic_redis_error_silently_noops(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.RedisError)):
            cache_set("MCDONALDS", "5814")

    def test_does_not_raise_on_redis_error(self):
        with patch.object(cache_module, "redis_client",
                          self._patched_client_that_raises(redis.RedisError)):
            try:
                cache_set("ANY KEY", "1234")
            except redis.RedisError:
                self.fail("cache_set raised RedisError — must fail open silently")


# ---------------------------------------------------------------------------
# Sentinel semantics — cache_get distinguishes miss from known-unknown
# ---------------------------------------------------------------------------

class SentinelSemanticTests(SimpleTestCase):
    """
    The caller (mcc_resolver) must be able to tell:
      None → cache miss (try next tier)
      ""   → known-unknown (skip LLM, return None)
      str  → real MCC (use it)
    """
    def test_miss_is_none_not_empty_string(self):
        with patch.object(cache_module, "redis_client", _make_client(None)):
            self.assertIsNone(cache_get("UNKNOWN"))

    def test_known_unknown_is_empty_string_not_none(self):
        with patch.object(cache_module, "redis_client", _make_client("")):
            result = cache_get("UNKNOWN")
        self.assertIsNotNone(result)
        self.assertEqual(result, "")

    def test_hit_is_non_empty_string(self):
        with patch.object(cache_module, "redis_client", _make_client("5814")):
            result = cache_get("MCDONALDS")
        self.assertTrue(result)

    def test_round_trip_set_then_get(self):
        """set then get with same key returns same value."""
        store = {}

        def fake_set(key, value, ex=None):
            store[key] = value

        def fake_get(key):
            return store.get(key)

        client = MagicMock()
        client.set.side_effect = fake_set
        client.get.side_effect = fake_get

        with patch.object(cache_module, "redis_client", client):
            cache_set("MCDONALDS", "5814")
            self.assertEqual(cache_get("MCDONALDS"), "5814")

    def test_round_trip_sentinel(self):
        store = {}

        def fake_set(key, value, ex=None):
            store[key] = value

        def fake_get(key):
            return store.get(key)

        client = MagicMock()
        client.set.side_effect = fake_set
        client.get.side_effect = fake_get

        with patch.object(cache_module, "redis_client", client):
            cache_set("MYSTERY", "")
            result = cache_get("MYSTERY")
        self.assertEqual(result, "")
