"""
merchant_cache tests.

Mock the module-level redis_client so tests never need a real Redis server.
"""

from unittest.mock import MagicMock, patch

import redis
from django.test import SimpleTestCase, override_settings

import services.merchant_cache as cache_module
from services.merchant_cache import cache_get, cache_set


def _make_client(get_return=None):
    client = MagicMock()
    client.get.return_value = get_return
    return client


class CacheKeyIsolationTests(SimpleTestCase):
    def test_two_users_read_different_keys(self):
        """A shared namespace would serve one user's label to everybody."""
        client = _make_client("dining")
        with patch.object(cache_module, "redis_client", client):
            cache_get(1, "AMAZON")
            cache_get(2, "AMAZON")
        self.assertEqual(
            [call.args[0] for call in client.get.call_args_list],
            ["merchant:1:AMAZON", "merchant:2:AMAZON"],
        )


class CacheGetHitTests(SimpleTestCase):
    def test_returns_category_on_hit(self):
        with patch.object(cache_module, "redis_client", _make_client("dining")):
            self.assertEqual(cache_get(7, "MCDONALDS"), "dining")

    def test_uses_namespaced_key(self):
        client = _make_client("dining")
        with patch.object(cache_module, "redis_client", client):
            cache_get(7, "MCDONALDS")
        client.get.assert_called_once_with("merchant:7:MCDONALDS")

    def test_returns_none_on_miss(self):
        with patch.object(cache_module, "redis_client", _make_client(None)):
            self.assertIsNone(cache_get(7, "UNKNOWN"))


class CacheGetFailOpenTests(SimpleTestCase):
    def test_connection_error_returns_none(self):
        client = MagicMock()
        client.get.side_effect = redis.ConnectionError("down")
        with patch.object(cache_module, "redis_client", client):
            self.assertIsNone(cache_get(7, "MCDONALDS"))

    def test_timeout_returns_none(self):
        client = MagicMock()
        client.get.side_effect = redis.TimeoutError("slow")
        with patch.object(cache_module, "redis_client", client):
            self.assertIsNone(cache_get(7, "MCDONALDS"))


class CacheSetTests(SimpleTestCase):
    @override_settings(MERCHANT_CACHE_TTL=3600)
    def test_stores_category_under_namespaced_key(self):
        client = MagicMock()
        with patch.object(cache_module, "redis_client", client):
            cache_set(7, "MCDONALDS", "dining")
        client.set.assert_called_once_with("merchant:7:MCDONALDS", "dining", ex=3600)

    def test_connection_error_is_swallowed(self):
        client = MagicMock()
        client.set.side_effect = redis.ConnectionError("down")
        with patch.object(cache_module, "redis_client", client):
            cache_set(7, "MCDONALDS", "dining")  # must not raise
