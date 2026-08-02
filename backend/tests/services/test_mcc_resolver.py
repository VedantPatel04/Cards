"""
resolve_mcc tests.

Tiers 1, 2, 5, 6 (budget=None keeps Tier 4 off).
Tiers 3a/3b/4 with mocked Redis + LLM (no real network).

The rules file is *data*, not fixture: tests inject their own rules dict so
editing merchant_rules.json can never break them. One test in
LoadMerchantRulesTests checks the real file's shape.
"""

import json
from unittest.mock import MagicMock, patch

import redis
from django.test import TestCase, override_settings

import seeds
import services.mcc_resolver as resolver_module
import services.merchant_cache as cache_module
from apps.transactions.models import MCC_Codes, MerchantResolution
from services.llm_client import LLMUnavailable
from services.mcc_resolver import (
    MERCHANT_RULES_PATH,
    REPRESENTATIVE_MCC,
    SOURCE_CATEGORY_MAP,
    _load_merchant_rules,
    known_mcc_codes,
    resolve_mcc,
)
from services.merchant_normalize import merchant_key
from services.upload_pipeline import UploadBudget


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Stand-in for merchant_rules.json. Keys must already be normalized
# (merchant_key output) or Tier 2 could never match them.
RULES = {
    "MCDONALDS": "5814",
    "WAL MART": "5411",
    "MTA": "4111",
    "LYFT": "4121",
    "DOMINOS PIZZA": "5814",
    "PERUSALL E BOOK": "5942",
}

# resolve_mcc only returns codes that exist in MCC_Codes, so every code any
# tier can produce has to be in the test catalog.
CATALOG_CODES = (
    "5814", "5411", "4111", "4121", "5942",              # rule targets
    "5812", "4789", "5999", "5541", "7999",              # Tier 5 representatives
)


def _reset_module_caches():
    """Reset module-level memo caches between tests so they don't bleed."""
    resolver_module.known_mcc_codes_cache = None
    resolver_module.merchant_rules = None


class ResolverTestCase(TestCase):
    """
    Shared setup: a seeded MCC catalog, an injected rules dict, and a Redis
    that always misses. Tests that care about Redis re-patch cache_get with a
    decorator, which takes precedence for the duration of the test method.
    """

    def setUp(self):
        _reset_module_caches()
        for code in CATALOG_CODES:
            seeds.make_mcc(code=code, category="other")

        self._patch(patch.object(resolver_module, "merchant_rules", RULES))
        # A developer machine may have a real Redis with real keys in it; pin the
        # cache to "always miss" so tier assertions are about the ladder only.
        self._patch(patch.object(resolver_module, "cache_get", return_value=None))
        self._patch(patch.object(resolver_module, "cache_set"))

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)


# ---------------------------------------------------------------------------
# known_mcc_codes()
# ---------------------------------------------------------------------------

class KnownMccCodesTests(TestCase):
    def setUp(self):
        _reset_module_caches()

    def test_returns_set(self):
        self.assertIsInstance(known_mcc_codes(), set)

    def test_contains_seeded_code(self):
        seeds.make_mcc(code="5814", category="dining")
        _reset_module_caches()
        self.assertIn("5814", known_mcc_codes())

    def test_does_not_contain_unseeded_code(self):
        self.assertNotIn("9999", known_mcc_codes())

    def test_is_memoized(self):
        """Second call must not hit the DB again."""
        seeds.make_mcc(code="5411", category="groceries")
        _reset_module_caches()
        first = known_mcc_codes()
        # add a new code after first call — memoized result must not reflect it
        seeds.make_mcc(code="0001", category="other")
        second = known_mcc_codes()
        self.assertIs(first, second)
        self.assertNotIn("0001", second)


# ---------------------------------------------------------------------------
# _load_merchant_rules()
# ---------------------------------------------------------------------------

class LoadMerchantRulesTests(TestCase):
    def setUp(self):
        _reset_module_caches()

    def test_returns_dict(self):
        self.assertIsInstance(_load_merchant_rules(), dict)

    def test_is_memoized(self):
        self.assertIs(_load_merchant_rules(), _load_merchant_rules())

    def test_missing_file_raises(self):
        with patch.object(resolver_module, "MERCHANT_RULES_PATH", "/nonexistent/path.json"):
            with self.assertRaises(FileNotFoundError):
                _load_merchant_rules()

    def test_non_object_json_raises(self):
        with patch("builtins.open", create=True):
            with patch("json.load", return_value=["not", "an", "object"]):
                with self.assertRaises(ValueError):
                    _load_merchant_rules()

    def test_real_file_is_usable(self):
        """
        Guards the data file itself: every key must already be a normalized
        merchant key and every value a string code, otherwise the rule is dead
        weight that can never match. Passes on an empty {} file.
        """
        with open(MERCHANT_RULES_PATH) as file:
            rules = json.load(file)
        self.assertIsInstance(rules, dict)
        for key, code in rules.items():
            with self.subTest(key=key):
                self.assertEqual(key, merchant_key(key))
                self.assertIsInstance(code, str)


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 1 (row already has a valid MCC)
# ---------------------------------------------------------------------------

class ResolveMccTier1Tests(ResolverTestCase):
    def test_tier1_valid_mcc_on_row_returned(self):
        row = {"raw_description": "SOME UNKNOWN MERCHANT", "mcc": "5814"}
        self.assertEqual(resolve_mcc(row), "5814")

    def test_tier1_beats_tier2_match(self):
        """Tier 1 wins even when Tier 2 would also match."""
        row = {"raw_description": "MCDONALD'S F31398", "mcc": "5411"}
        self.assertEqual(resolve_mcc(row), "5411")

    def test_tier1_invalid_mcc_falls_through(self):
        """mcc not in MCC_Codes → skip Tier 1, continue to lower tiers."""
        row = {"raw_description": "MCDONALD'S F31398", "mcc": "9999"}
        self.assertEqual(resolve_mcc(row), "5814")  # Tier 2 answer

    def test_tier1_tolerates_whitespace_and_non_string(self):
        self.assertEqual(resolve_mcc({"raw_description": "X", "mcc": " 5814 "}), "5814")
        self.assertEqual(resolve_mcc({"raw_description": "X", "mcc": 5814}), "5814")

    def test_tier1_none_mcc_falls_through(self):
        row = {"raw_description": "MCDONALD'S F31398"}  # no mcc key
        self.assertEqual(resolve_mcc(row), "5814")


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 2 (merchant_rules.json exact match)
# ---------------------------------------------------------------------------

class ResolveMccTier2Tests(ResolverTestCase):
    def test_mcdonalds_via_raw_description(self):
        self.assertEqual(resolve_mcc({"raw_description": "MCDONALD'S F31398"}), "5814")

    def test_store_variant_also_resolves(self):
        """Different store code, same normalized key → same answer."""
        self.assertEqual(
            resolve_mcc({"raw_description": "MCDONALD'S F31398"}),
            resolve_mcc({"raw_description": "MCDONALD'S F25696"}),
        )

    def test_wal_mart_hash_variant(self):
        self.assertEqual(resolve_mcc({"raw_description": "WAL-MART #2297"}), "5411")

    def test_mta_star_variant(self):
        self.assertEqual(resolve_mcc({"raw_description": "MTA*NYCT PAYGO"}), "4111")

    def test_lyft_star_variant(self):
        self.assertEqual(resolve_mcc({"raw_description": "LYFT   *AIRPORT 07-06"}), "4121")

    def test_dominos_hash_variant(self):
        self.assertEqual(resolve_mcc({"raw_description": "DOMINOS PIZZA #10278"}), "5814")

    def test_perusall(self):
        self.assertEqual(resolve_mcc({"raw_description": "PERUSALL E-BOOK"}), "5942")

    def test_unknown_merchant_does_not_return_from_tier2(self):
        row = {"raw_description": "TOTALLY UNKNOWN MERCHANT XYZ"}
        # no rule match → falls through; no source_category → None
        self.assertIsNone(resolve_mcc(row))

    def test_empty_rules_file_is_not_an_error(self):
        """A stripped merchant_rules.json just means every row falls to Tier 5."""
        with patch.object(resolver_module, "merchant_rules", {}):
            row = {"raw_description": "MCDONALD'S F31398", "source_category": "Food & Drink"}
            self.assertEqual(resolve_mcc(row), "5812")  # Tier 5, not Tier 2

    def test_rule_pointing_at_unknown_code_is_discarded(self):
        """
        A typo'd rule must not reach the DB: Transactions.mcc_code is a FK, so
        returning a code MCC_Codes lacks would break the whole upload's write.
        """
        with patch.object(resolver_module, "merchant_rules", {"MCDONALDS": "9999"}):
            self.assertIsNone(resolve_mcc({"raw_description": "MCDONALD'S F31398"}))


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 5 (source_category fallback)
# ---------------------------------------------------------------------------

class ResolveMccTier5Tests(ResolverTestCase):
    def test_groceries_category_returns_5411(self):
        row = {"raw_description": "TOTALLY UNKNOWN STORE", "source_category": "Groceries"}
        self.assertEqual(resolve_mcc(row), "5411")

    def test_food_and_drink_returns_5812(self):
        row = {"raw_description": "TOTALLY UNKNOWN RESTAURANT", "source_category": "Food & Drink"}
        self.assertEqual(resolve_mcc(row), "5812")

    def test_travel_returns_4789(self):
        row = {"raw_description": "UNKNOWN TRAVEL MERCHANT", "source_category": "Travel"}
        self.assertEqual(resolve_mcc(row), "4789")

    def test_shopping_returns_5999(self):
        row = {"raw_description": "RANDOM SHOP", "source_category": "Shopping"}
        self.assertEqual(resolve_mcc(row), "5999")

    def test_fees_and_adjustments_returns_none(self):
        """'other' canonical maps to None in REPRESENTATIVE_MCC → Tier 5 returns None."""
        row = {"raw_description": "FOREIGN TRANSACTION FEE", "source_category": "Fees & Adjustments"}
        self.assertIsNone(resolve_mcc(row))

    def test_unrecognized_category_falls_to_tier6(self):
        row = {"raw_description": "SOME MERCHANT", "source_category": "Utilities"}
        self.assertIsNone(resolve_mcc(row))

    def test_tier2_beats_tier5(self):
        """Tier 2 match (MCDONALDS→5814) beats Tier 5 category guess (dining→5812)."""
        row = {
            "raw_description": "MCDONALD'S F31398",
            "source_category": "Food & Drink",  # would give 5812 via Tier 5
        }
        self.assertEqual(resolve_mcc(row), "5814")

    def test_every_representative_code_is_in_the_catalog(self):
        """
        REPRESENTATIVE_MCC is hand-written; if one of its codes is not a real
        MCC_Codes row, that whole category silently stops categorizing.
        """
        for category, code in REPRESENTATIVE_MCC.items():
            if code is None:
                continue
            with self.subTest(category=category):
                self.assertIn(code, known_mcc_codes())

    def test_every_source_category_maps_to_a_known_bucket(self):
        for source, canonical in SOURCE_CATEGORY_MAP.items():
            with self.subTest(source=source):
                self.assertIn(canonical, REPRESENTATIVE_MCC)

    def test_canonical_category_from_adapter_is_used_directly(self):
        """
        The shape every adapter (Chase today, Plaid next) hands us: a canonical
        category, no provider vocabulary for the resolver to interpret.
        """
        row = {"raw_description": "SOME UNKNOWN PLACE", "category": "groceries"}
        self.assertEqual(resolve_mcc(row), "5411")

    def test_canonical_category_wins_over_raw_source_category(self):
        row = {
            "raw_description": "SOME UNKNOWN PLACE",
            "category": "groceries",       # adapter's answer
            "source_category": "Travel",   # raw provider text, kept for debugging
        }
        self.assertEqual(resolve_mcc(row), "5411")

    def test_unmapped_canonical_category_falls_to_tier6(self):
        row = {"raw_description": "SOME UNKNOWN PLACE", "category": "crypto"}
        self.assertIsNone(resolve_mcc(row))


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 6 (nothing matched → None)
# ---------------------------------------------------------------------------

class ResolveMccTier6Tests(ResolverTestCase):
    def test_no_mcc_no_rule_no_category_returns_none(self):
        self.assertIsNone(resolve_mcc({"raw_description": "COMPLETELY UNKNOWN @@@"}))

    def test_empty_row_does_not_raise(self):
        self.assertIsNone(resolve_mcc({}))

    def test_return_type_is_always_str_or_none(self):
        rows = [
            {"raw_description": "MCDONALD'S F31398"},
            {"raw_description": "UNKNOWN", "source_category": "Groceries"},
            {"raw_description": "UNKNOWN", "source_category": "Fees & Adjustments"},
            {"raw_description": "GARBAGE !!!"},
            {},
        ]
        for row in rows:
            with self.subTest(row=row):
                self.assertIsInstance(resolve_mcc(row), (str, type(None)))


# ---------------------------------------------------------------------------
# resolve_mcc — descriptions that normalize to an empty key
# ---------------------------------------------------------------------------

class ResolveMccEmptyKeyTests(ResolverTestCase):
    """
    "12345" and "$$$" both normalize to "". Those rows must not share one cache
    entry / one MerchantResolution row, so tiers 2-4 are skipped entirely.
    """

    @patch("services.llm_client.llm_lookup_mcc")
    def test_empty_key_skips_cache_and_llm(self, mock_llm):
        row = {"raw_description": "12345", "source_category": "Groceries"}
        with patch.object(resolver_module, "cache_get") as mock_get:
            self.assertEqual(resolve_mcc(row, budget=UploadBudget(5)), "5411")  # Tier 5
        mock_get.assert_not_called()
        mock_llm.assert_not_called()

    @patch("services.llm_client.llm_lookup_mcc")
    def test_empty_key_without_category_returns_none(self, mock_llm):
        self.assertIsNone(resolve_mcc({"raw_description": "$$$"}, budget=UploadBudget(5)))
        mock_llm.assert_not_called()
        self.assertFalse(MerchantResolution.objects.filter(merchant_key="").exists())


# ---------------------------------------------------------------------------
# resolve_mcc — full Chase CSV rows
# ---------------------------------------------------------------------------

class ResolveMccChaseRowTests(ResolverTestCase):
    """
    Feed normalized rows from the sample Chase CSV and assert which tier wins.
    """

    def test_mcdonalds_f31398(self):
        row = {"raw_description": "MCDONALD'S F31398", "source_category": "Food & Drink"}
        self.assertEqual(resolve_mcc(row), "5814")  # Tier 2

    def test_mcdonalds_f25696(self):
        row = {"raw_description": "MCDONALD'S F25696", "source_category": "Food & Drink"}
        self.assertEqual(resolve_mcc(row), "5814")  # Tier 2

    def test_walmart_2297(self):
        row = {"raw_description": "WAL-MART #2297", "source_category": "Groceries"}
        self.assertEqual(resolve_mcc(row), "5411")  # Tier 2 (not Tier 5)

    def test_mta_star_nyct(self):
        row = {"raw_description": "MTA*NYCT PAYGO", "source_category": "Travel"}
        self.assertEqual(resolve_mcc(row), "4111")  # Tier 2

    def test_lyft_airport(self):
        row = {"raw_description": "LYFT   *AIRPORT 07-06", "source_category": "Travel"}
        self.assertEqual(resolve_mcc(row), "4121")  # Tier 2

    def test_lyft_waitsave(self):
        row = {"raw_description": "LYFT   *WAITSAVE 07-06", "source_category": "Travel"}
        self.assertEqual(resolve_mcc(row), "4121")  # Tier 2

    def test_perusall_ebook(self):
        row = {"raw_description": "PERUSALL E-BOOK", "source_category": "Shopping"}
        self.assertEqual(resolve_mcc(row), "5942")  # Tier 2

    def test_dominos_pizza(self):
        row = {"raw_description": "DOMINOS PIZZA #10278", "source_category": "Food & Drink"}
        self.assertEqual(resolve_mcc(row), "5814")  # Tier 2

    def test_pmusa_unknown_merchant_travel(self):
        """PMUSA not in rules → Tier 5 travel fallback."""
        row = {"raw_description": "PMUSA 304046 JERSEY CI", "source_category": "Travel"}
        self.assertEqual(resolve_mcc(row), "4789")  # Tier 5

    def test_foreign_transaction_fee(self):
        """Fee → 'other' → None."""
        row = {"raw_description": "FOREIGN TRANSACTION FEE", "source_category": "Fees & Adjustments"}
        self.assertIsNone(resolve_mcc(row))


# ---------------------------------------------------------------------------
# Tier 3a — Redis
# ---------------------------------------------------------------------------

class ResolveMccTier3aRedisTests(ResolverTestCase):
    """Unknown merchant (no Tier 2 rule) so Redis is actually consulted."""

    UNKNOWN = {"raw_description": "WEIRD UNKNOWN CAFE XYZ", "source_category": "Food & Drink"}

    @patch.object(resolver_module, "cache_get", return_value="5814")
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc")
    def test_redis_hit_returns_mcc_and_skips_llm(self, mock_llm, mock_set, mock_get):
        budget = UploadBudget(5)
        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=budget), "5814")
        mock_get.assert_called_once()
        mock_set.assert_not_called()
        mock_llm.assert_not_called()
        self.assertEqual(budget.remaining, 5)  # must not spend on cache hit

    @patch.object(resolver_module, "cache_get", return_value="")
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc")
    def test_redis_sentinel_returns_none_skips_llm_and_tier5(self, mock_llm, mock_set, mock_get):
        """'' means known-unknown — return None, do not fall to Tier 5 dining."""
        budget = UploadBudget(5)
        self.assertIsNone(resolve_mcc(self.UNKNOWN, budget=budget))
        mock_llm.assert_not_called()
        mock_set.assert_not_called()
        self.assertEqual(budget.remaining, 5)

    @patch.object(resolver_module, "cache_get", return_value="9999")
    def test_stale_cached_code_is_discarded(self, mock_get):
        """A code that has since left MCC_Codes must not reach the FK write."""
        self.assertIsNone(resolve_mcc(self.UNKNOWN))

    def test_dead_redis_still_resolves(self):
        """
        With Redis down the real cache_get/cache_set fail open (None / no-op),
        so the ladder must still produce its deterministic answers.
        """
        dead_client = MagicMock()
        dead_client.get.side_effect = redis.ConnectionError
        dead_client.set.side_effect = redis.ConnectionError

        # real cache functions, backed by a broken client
        with patch.object(resolver_module, "cache_get", cache_module.cache_get), \
             patch.object(resolver_module, "cache_set", cache_module.cache_set), \
             patch.object(cache_module, "redis_client", dead_client):
            self.assertEqual(
                resolve_mcc({"raw_description": "WAL-MART #2297"}), "5411"  # Tier 2
            )
            self.assertEqual(resolve_mcc(self.UNKNOWN), "5812")  # Tier 5


# ---------------------------------------------------------------------------
# Tier 3b — MerchantResolution DB
# ---------------------------------------------------------------------------

class ResolveMccTier3bDbTests(ResolverTestCase):
    UNKNOWN = {"raw_description": "WEIRD UNKNOWN CAFE XYZ", "source_category": "Food & Drink"}

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    def test_db_hit_returns_mcc_and_warms_redis(self, mock_set, mock_get):
        key = merchant_key(self.UNKNOWN["raw_description"])
        MerchantResolution.objects.create(merchant_key=key, mcc_code_id="5814", source="llm")
        self.assertEqual(resolve_mcc(self.UNKNOWN), "5814")
        mock_set.assert_called_once_with(key, "5814")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    def test_db_hit_with_null_mcc_warms_sentinel(self, mock_set, mock_get):
        key = merchant_key(self.UNKNOWN["raw_description"])
        MerchantResolution.objects.create(merchant_key=key, mcc_code=None, source="llm")
        self.assertIsNone(resolve_mcc(self.UNKNOWN))
        mock_set.assert_called_once_with(key, "")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch("services.llm_client.llm_lookup_mcc")
    def test_db_hit_skips_llm_even_with_budget(self, mock_llm, mock_get):
        key = merchant_key(self.UNKNOWN["raw_description"])
        MerchantResolution.objects.create(merchant_key=key, mcc_code_id="5814", source="llm")
        budget = UploadBudget(5)
        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=budget), "5814")
        mock_llm.assert_not_called()
        self.assertEqual(budget.remaining, 5)


# ---------------------------------------------------------------------------
# Tier 4 — LLM + budget
# ---------------------------------------------------------------------------

@override_settings(LLM_ENABLED=True, LLM_API_KEY="test-key")
class ResolveMccTier4LlmTests(ResolverTestCase):
    UNKNOWN = {"raw_description": "WEIRD UNKNOWN CAFE XYZ", "source_category": "Food & Drink"}

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", return_value="5814")
    def test_cold_miss_with_budget_calls_llm_persists_and_caches(
        self, mock_llm, mock_set, mock_get
    ):
        key = merchant_key(self.UNKNOWN["raw_description"])
        budget = UploadBudget(3)

        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=budget), "5814")
        mock_llm.assert_called_once_with(key)
        self.assertEqual(budget.remaining, 2)

        stored = MerchantResolution.objects.get(merchant_key=key)
        self.assertEqual(stored.mcc_code_id, "5814")
        self.assertEqual(stored.source, "llm")
        mock_set.assert_called_once_with(key, "5814")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", return_value=None)
    def test_llm_none_still_persists_and_caches_sentinel(self, mock_llm, mock_set, mock_get):
        key = merchant_key(self.UNKNOWN["raw_description"])
        budget = UploadBudget(1)

        self.assertIsNone(resolve_mcc(self.UNKNOWN, budget=budget))
        stored = MerchantResolution.objects.get(merchant_key=key)
        self.assertIsNone(stored.mcc_code_id)
        mock_set.assert_called_once_with(key, "")
        self.assertEqual(budget.remaining, 0)

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch("services.llm_client.llm_lookup_mcc")
    def test_budget_none_or_exhausted_skips_llm_falls_to_tier5(self, mock_llm, mock_get):
        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=None), "5812")
        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=UploadBudget(0)), "5812")
        mock_llm.assert_not_called()

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch("services.llm_client.llm_lookup_mcc")
    def test_tier2_rule_beats_cache_and_llm(self, mock_llm, mock_get):
        row = {"raw_description": "MCDONALD'S F31398", "source_category": "Food & Drink"}
        self.assertEqual(resolve_mcc(row, budget=UploadBudget(5)), "5814")
        mock_llm.assert_not_called()
        mock_get.assert_not_called()

    @override_settings(LLM_ENABLED=False, LLM_API_KEY="")
    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc")
    def test_llm_disabled_skips_tier4_falls_to_tier5(self, mock_llm, mock_set, mock_get):
        """Off/unkeyed LLM must not persist a known-unknown or burn budget."""
        budget = UploadBudget(5)
        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=budget), "5812")
        mock_llm.assert_not_called()
        mock_set.assert_not_called()
        self.assertEqual(budget.remaining, 5)
        self.assertEqual(MerchantResolution.objects.count(), 0)

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", side_effect=LLMUnavailable("down"))
    def test_provider_outage_falls_to_tier5_without_persisting(
        self, mock_llm, mock_set, mock_get
    ):
        """
        A blip must not brand the merchant unknown: no MerchantResolution row,
        no cached sentinel, so the next upload retries it for real.
        """
        budget = UploadBudget(5)
        self.assertEqual(resolve_mcc(self.UNKNOWN, budget=budget), "5812")
        self.assertEqual(MerchantResolution.objects.count(), 0)
        mock_set.assert_not_called()
        # Budget still spent, so a total outage cannot hang on every merchant.
        self.assertEqual(budget.remaining, 4)

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", return_value="5814")
    def test_resolution_row_records_category_and_confidence(
        self, mock_llm, mock_set, mock_get
    ):
        """Reward matching reads categories, so the denormalized copy must be set."""
        MCC_Codes.objects.filter(code="5814").update(category="dining")

        resolve_mcc(self.UNKNOWN, budget=UploadBudget(1))

        stored = MerchantResolution.objects.get(
            merchant_key=merchant_key(self.UNKNOWN["raw_description"])
        )
        self.assertEqual(stored.category, "dining")
        self.assertEqual(stored.confidence, resolver_module.LLM_CONFIDENCE)

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", return_value=None)
    def test_known_unknown_row_has_zero_confidence(self, mock_llm, mock_set, mock_get):
        resolve_mcc(self.UNKNOWN, budget=UploadBudget(1))
        stored = MerchantResolution.objects.get(
            merchant_key=merchant_key(self.UNKNOWN["raw_description"])
        )
        self.assertEqual(stored.category, "")
        self.assertEqual(stored.confidence, 0.0)
