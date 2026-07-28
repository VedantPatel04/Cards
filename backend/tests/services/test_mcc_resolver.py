"""
Phase 2 — resolve_mcc tests (Tiers 1, 2, 5, 6).

Tiers 3/4 (Redis + LLM) are not implemented yet; tests stub them out
by simply not providing a budget, which keeps Phase 2 free / no external deps.

DB is required only for Tier 1 (known_mcc_codes() queries MCC_Codes).
Tiers 2/5/6 are data-driven (JSON + dicts); they can run in a TestCase too.
"""

import json
import os
from unittest.mock import patch

from django.test import TestCase

import seeds
import services.mcc_resolver as resolver_module
from services.mcc_resolver import (
    REPRESENTATIVE_MCC,
    SOURCE_CATEGORY_MAP,
    _load_merchant_rules,
    known_mcc_codes,
    resolve_mcc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_module_caches():
    """Reset module-level memo caches between tests so they don't bleed."""
    resolver_module.known_mcc_codes_cache = None
    resolver_module.merchant_rules = None


# ---------------------------------------------------------------------------
# known_mcc_codes()
# ---------------------------------------------------------------------------

class KnownMccCodesTests(TestCase):
    def setUp(self):
        _reset_module_caches()

    def test_returns_set(self):
        result = known_mcc_codes()
        self.assertIsInstance(result, set)

    def test_contains_seeded_code(self):
        seeds.make_mcc(code="5814", category="dining")
        _reset_module_caches()
        self.assertIn("5814", known_mcc_codes())

    def test_does_not_contain_unseeded_code(self):
        _reset_module_caches()
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

    def test_contains_expected_keys(self):
        rules = _load_merchant_rules()
        for key in ("MCDONALDS", "WAL MART", "MTA", "LYFT", "DOMINOS PIZZA", "PERUSALL E BOOK"):
            with self.subTest(key=key):
                self.assertIn(key, rules)

    def test_values_are_strings(self):
        for key, val in _load_merchant_rules().items():
            with self.subTest(key=key):
                self.assertIsInstance(val, str)

    def test_is_memoized(self):
        first = _load_merchant_rules()
        second = _load_merchant_rules()
        self.assertIs(first, second)

    def test_mcdonalds_maps_to_5814(self):
        self.assertEqual(_load_merchant_rules()["MCDONALDS"], "5814")

    def test_missing_file_raises(self):
        _reset_module_caches()
        with patch.object(resolver_module, "MERCHANT_RULES_PATH", "/nonexistent/path.json"):
            with self.assertRaises(FileNotFoundError):
                _load_merchant_rules()


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 1 (row already has a valid MCC)
# ---------------------------------------------------------------------------

class ResolveMccTier1Tests(TestCase):
    def setUp(self):
        _reset_module_caches()
        seeds.make_mcc(code="5814", category="dining")
        seeds.make_mcc(code="5411", category="groceries")

    def test_tier1_valid_mcc_on_row_returned(self):
        row = {"raw_description": "SOME UNKNOWN MERCHANT", "mcc": "5814"}
        self.assertEqual(resolve_mcc(row), "5814")

    def test_tier1_beats_tier2_match(self):
        """Tier 1 wins even when Tier 2 would also match."""
        # MCDONALDS is in merchant_rules.json → "5814"
        # row carries mcc "5411" (grocery). Tier 1 should win.
        row = {"raw_description": "MCDONALD'S F31398", "mcc": "5411"}
        self.assertEqual(resolve_mcc(row), "5411")

    def test_tier1_invalid_mcc_falls_through(self):
        """mcc not in MCC_Codes → skip Tier 1, continue to lower tiers."""
        row = {
            "raw_description": "MCDONALD'S F31398",  # hits Tier 2
            "mcc": "9999",                            # not in DB
        }
        self.assertEqual(resolve_mcc(row), "5814")    # Tier 2 answer

    def test_tier1_none_mcc_falls_through(self):
        row = {"raw_description": "MCDONALD'S F31398"}  # no mcc key
        self.assertEqual(resolve_mcc(row), "5814")


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 2 (merchant_rules.json exact match)
# ---------------------------------------------------------------------------

class ResolveMccTier2Tests(TestCase):
    def setUp(self):
        _reset_module_caches()

    def test_mcdonalds_via_raw_description(self):
        row = {"raw_description": "MCDONALD'S F31398"}
        self.assertEqual(resolve_mcc(row), "5814")

    def test_store_variant_also_resolves(self):
        """Different store code, same normalized key → same answer."""
        self.assertEqual(
            resolve_mcc({"raw_description": "MCDONALD'S F31398"}),
            resolve_mcc({"raw_description": "MCDONALD'S F25696"}),
        )

    def test_wal_mart_hash_variant(self):
        row = {"raw_description": "WAL-MART #2297"}
        self.assertEqual(resolve_mcc(row), "5411")

    def test_mta_star_variant(self):
        row = {"raw_description": "MTA*NYCT PAYGO"}
        self.assertEqual(resolve_mcc(row), "4111")

    def test_lyft_star_variant(self):
        row = {"raw_description": "LYFT   *AIRPORT 07-06"}
        self.assertEqual(resolve_mcc(row), "4121")

    def test_dominos_hash_variant(self):
        row = {"raw_description": "DOMINOS PIZZA #10278"}
        self.assertEqual(resolve_mcc(row), "5814")

    def test_perusall(self):
        row = {"raw_description": "PERUSALL E-BOOK"}
        self.assertEqual(resolve_mcc(row), "5942")

    def test_unknown_merchant_does_not_return_from_tier2(self):
        row = {"raw_description": "TOTALLY UNKNOWN MERCHANT XYZ"}
        # no rule match → falls through; no source_category → None
        self.assertIsNone(resolve_mcc(row))

    def test_empty_description_does_not_raise(self):
        row = {"raw_description": ""}
        result = resolve_mcc(row)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 5 (source_category fallback)
# ---------------------------------------------------------------------------

class ResolveMccTier5Tests(TestCase):
    def setUp(self):
        _reset_module_caches()

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
        self.assertEqual(resolve_mcc(row), "5814")  # Tier 2 wins

    def test_tier5_used_only_when_tier2_misses(self):
        """Unknown merchant + known category → Tier 5 fires."""
        row = {
            "raw_description": "WEIRD GROCERY CO",
            "source_category": "Groceries",
        }
        self.assertEqual(resolve_mcc(row), "5411")


# ---------------------------------------------------------------------------
# resolve_mcc — Tier 6 (nothing matched → None)
# ---------------------------------------------------------------------------

class ResolveMccTier6Tests(TestCase):
    def setUp(self):
        _reset_module_caches()

    def test_no_mcc_no_rule_no_category_returns_none(self):
        row = {"raw_description": "COMPLETELY UNKNOWN @@@"}
        self.assertIsNone(resolve_mcc(row))

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
                result = resolve_mcc(row)
                self.assertIsInstance(result, (str, type(None)))


# ---------------------------------------------------------------------------
# resolve_mcc — full Chase CSV rows
# ---------------------------------------------------------------------------

class ResolveMccChaseRowTests(TestCase):
    """
    End-to-end: feed normalized rows from the sample Chase CSV and assert
    correct tier resolution. Mirrors the Phase 2 checkpoint in the plan.
    """
    def setUp(self):
        _reset_module_caches()

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
        self.assertIsNone(resolve_mcc(row))  # Tier 5 returns None for "other"
