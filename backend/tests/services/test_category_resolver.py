"""
resolve_category tests.

resolve_category() now returns a ResolutionResult(category, source, confidence)
instead of a plain string. Tests assert on all three fields where relevant.
"""

from unittest.mock import MagicMock, patch

import redis
from django.test import TestCase

import seeds
import services.category_resolver as resolver_module
import services.merchant_cache as cache_module
from apps.transactions.models import (
    SOURCE_BANK,
    SOURCE_GLOBAL,
    SOURCE_USER,
    UNRESOLVED_CATEGORY,
    GlobalMerchantAlias,
    MerchantResolution,
)
from services.category_resolver import (
    UNRESOLVED_RESULT,
    ResolutionResult,
    invalidate_global_alias_cache,
    is_valid_category,
    resolve_category,
    reward_categories,
)
from services.merchant_normalize import merchant_key


class ResolverTestCase(TestCase):
    """Redis is mocked out and global alias cache is cleared for every test."""

    def setUp(self):
        resolver_module._reward_categories = None
        invalidate_global_alias_cache()
        self.user = seeds.make_user()
        self._patch(patch.object(resolver_module, "cache_get", return_value=None))
        self._patch(patch.object(resolver_module, "cache_set"))

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)


class RewardCategoriesTests(TestCase):
    def setUp(self):
        resolver_module._reward_categories = None

    def test_vocabulary_includes_all_buckets(self):
        for expected in ("dining", "groceries", "travel", "gas", "entertainment", "shopping", "other"):
            self.assertIn(expected, reward_categories())


class ResolveCategoryResultTypeTests(ResolverTestCase):
    def test_returns_resolution_result_namedtuple(self):
        result = resolve_category(
            {"raw_description": "STARBUCKS", "category": "dining"}, self.user.pk
        )
        self.assertIsInstance(result, ResolutionResult)
        self.assertIsInstance(result.category, str)
        self.assertIsInstance(result.source, str)
        self.assertIsInstance(result.confidence, float)


class ResolveCategoryAdapterTierTests(ResolverTestCase):
    def test_adapter_category_returned_with_bank_source(self):
        result = resolve_category(
            {"raw_description": "UNKNOWN CAFE", "category": "dining"}, self.user.pk
        )
        self.assertEqual(result.category, "dining")
        self.assertEqual(result.source, SOURCE_BANK)
        self.assertEqual(result.confidence, 0.7)

    def test_blank_adapter_category_is_unresolved(self):
        result = resolve_category(
            {"raw_description": "WEIRD UNKNOWN VENDOR", "category": ""}, self.user.pk
        )
        self.assertEqual(result, UNRESOLVED_RESULT)

    def test_invalid_adapter_category_is_unresolved(self):
        result = resolve_category(
            {"raw_description": "WEIRD", "category": "crypto"}, self.user.pk
        )
        self.assertEqual(result.category, UNRESOLVED_CATEGORY)

    def test_unidentifiable_merchant_is_other_not_unresolved(self):
        result = resolve_category({"raw_description": "", "category": ""}, self.user.pk)
        self.assertEqual(result.category, "other")

    def test_adapter_category_not_used_when_merchant_has_global_alias(self):
        """Global tier (confidence 0.9) beats the bank's assignment (0.7)."""
        GlobalMerchantAlias.objects.create(
            merchant_key="STARBUCKS", canonical_name="Starbucks", category="dining"
        )
        invalidate_global_alias_cache()
        result = resolve_category(
            {"raw_description": "STARBUCKS", "category": "shopping"}, self.user.pk
        )
        self.assertEqual(result.category, "dining")
        self.assertEqual(result.source, SOURCE_GLOBAL)
        self.assertEqual(result.confidence, 0.9)


class ResolveCategoryGlobalAliasTierTests(ResolverTestCase):
    def setUp(self):
        super().setUp()
        GlobalMerchantAlias.objects.create(
            merchant_key="MYSTERY VENDOR", canonical_name="Mystery Vendor", category="entertainment"
        )
        invalidate_global_alias_cache()

    def test_global_alias_resolves_unknown_bank_category(self):
        result = resolve_category(
            {"raw_description": "MYSTERY VENDOR", "category": ""}, self.user.pk
        )
        self.assertEqual(result.category, "entertainment")
        self.assertEqual(result.source, SOURCE_GLOBAL)

    def test_user_override_beats_global_alias(self):
        key = merchant_key("MYSTERY VENDOR")
        seeds.make_merchant_resolution(user=self.user, merchant_key=key, category="shopping")
        result = resolve_category(
            {"raw_description": "MYSTERY VENDOR", "category": ""}, self.user.pk
        )
        self.assertEqual(result.category, "shopping")
        self.assertEqual(result.source, SOURCE_USER)
        self.assertEqual(result.confidence, 1.0)


class ResolveCategoryUserOverrideTierTests(ResolverTestCase):
    ROW = {"raw_description": "WEIRD UNKNOWN CAFE XYZ", "category": "dining"}

    @patch.object(resolver_module, "cache_get", return_value="groceries")
    @patch.object(resolver_module, "cache_set")
    def test_redis_override_wins_with_user_source(self, mock_set, mock_get):
        result = resolve_category(self.ROW, self.user.pk)
        self.assertEqual(result.category, "groceries")
        self.assertEqual(result.source, SOURCE_USER)
        self.assertEqual(result.confidence, 1.0)
        mock_set.assert_not_called()

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    def test_db_override_warms_redis(self, mock_set, mock_get):
        key = merchant_key(self.ROW["raw_description"])
        seeds.make_merchant_resolution(user=self.user, merchant_key=key, category="gas")
        result = resolve_category(self.ROW, self.user.pk)
        self.assertEqual(result.category, "gas")
        self.assertEqual(result.source, SOURCE_USER)
        mock_set.assert_called_once_with(self.user.pk, key, "gas")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    def test_another_users_override_is_not_applied(self, mock_set, mock_get):
        other = seeds.make_user()
        key = merchant_key(self.ROW["raw_description"])
        seeds.make_merchant_resolution(user=other, merchant_key=key, category="gas")
        result = resolve_category(self.ROW, self.user.pk)
        self.assertEqual(result.source, SOURCE_BANK)  # fell through to bank
        self.assertEqual(result.category, "dining")

    @patch.object(resolver_module, "cache_get", return_value="not-a-real-bucket")
    def test_stale_redis_value_ignored(self, mock_get):
        result = resolve_category(self.ROW, self.user.pk)
        self.assertEqual(result.source, SOURCE_BANK)

    def test_dead_redis_still_resolves(self):
        dead = MagicMock()
        dead.get.side_effect = redis.ConnectionError
        dead.set.side_effect = redis.ConnectionError
        with patch.object(resolver_module, "cache_get", cache_module.cache_get), \
             patch.object(resolver_module, "cache_set", cache_module.cache_set), \
             patch.object(cache_module, "redis_client", dead):
            result = resolve_category(self.ROW, self.user.pk)
        self.assertEqual(result.category, "dining")

    def test_dead_redis_still_reads_db_override(self):
        key = merchant_key(self.ROW["raw_description"])
        MerchantResolution.objects.create(
            user=self.user, merchant_key=key, category="gas", source="user"
        )
        dead = MagicMock()
        dead.get.side_effect = redis.ConnectionError
        dead.set.side_effect = redis.ConnectionError
        with patch.object(resolver_module, "cache_get", cache_module.cache_get), \
             patch.object(resolver_module, "cache_set", cache_module.cache_set), \
             patch.object(cache_module, "redis_client", dead):
            result = resolve_category(self.ROW, self.user.pk)
        self.assertEqual(result.category, "gas")
        self.assertEqual(result.source, SOURCE_USER)
