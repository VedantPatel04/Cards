"""
Phases 2 & 6 — Tiered Approach to the MCC resolver.

Takes an already-normalized row (produced by the CSV adapter) and returns an
MCC code that exists in MCC_Codes, or None. The adapter decides the file
format; this file decides categorization, so nothing here is Chase-specific.

Tier order:
  1. MCC already on the row (tester CSV)
  2. merchant_rules.json keyword match
  3. Redis GET -> MerchantResolution DB row
  4. LLM call (only if budget remains) -> write both
  5. source_category -> representative MCC
  6. None
"""

import json
import os
from django.conf import settings
from services.merchant_normalize import merchant_key
# from services.merchant_cache import cache_get, cache_set
# from services.llm_client import llm_lookup_mcc
from apps.transactions.models import MCC_Codes, MerchantResolution

MERCHANT_RULES_PATH = os.path.join(
    settings.BASE_DIR, "data", "card_catalog", "merchant_rules.json"
)

# Tier 5 fallback: broadest/catch-all code inside each category bucket per
# mcc_category_map.json. Used when we know *what kind* of merchant it is
# but not the exact MCC (e.g. Chase gives "Travel" but not "Airlines" vs
# "Parking"). "other" maps to None -> mcc_code stays NULL on the transaction.
REPRESENTATIVE_MCC = {
    "groceries": "5411",      # Grocery Stores and Supermarkets
    "dining": "5812",         # Eating Places and Restaurants (broadest sit-down)
    "travel": "4789",         # Transportation Services – Not Elsewhere Classified
    "gas": "5541",            # Service Stations
    "shopping": "5999",       # Miscellaneous and Specialty Retail Stores
    "entertainment": "7999",  # Recreation Services – Not Elsewhere Classified
    "other": None,
}

# Chase-specific: maps the text in Chase's "Category" column to our canonical
# category vocabulary. Will moves to the Chase adapter once
# Plaid is added (each adapter will own its own mapping).
SOURCE_CATEGORY_MAP = {
    "Groceries": "groceries",
    "Food & Drink": "dining",
    "Travel": "travel",
    "Shopping": "shopping",
    "Fees & Adjustments": "other",
}

known_mcc_codes_cache = None
def known_mcc_codes() -> set[str]:
    """
    Return the set of valid MCC codes (from MCC_Codes). Used by Tier 1 and to
    validate LLM output. Cache in a module-level variable so it's queried once.
    """
    global known_mcc_codes_cache
    if known_mcc_codes_cache is None:
        known_mcc_codes_cache = set(MCC_Codes.objects.values_list("code", flat=True))
    return known_mcc_codes_cache

merchant_rules = None
def _load_merchant_rules() -> dict:
    """Load and memoize merchant_rules.json ({KEYWORD: MCC})."""
    global merchant_rules
    if merchant_rules is None:
        with open(MERCHANT_RULES_PATH, "r") as file:        
            merchant_rules = json.load(file)
    return merchant_rules

def resolve_mcc(row: dict, budget=None) -> str | None:
    """
    Resolve an MCC code for one normalized row.

    Expected row keys (from the adapter):
      raw_description : str   (required)
      source_category : str   (optional; drives Tier 5)
      mcc             : str   (optional; drives Tier 1)

    `budget` is an optional per-upload counter object (see pipeline) whose
    .allows() / .spend() gate the paid Tier 4 call. When None, treat Tier 4
    as disabled.

    Returns a valid MCC code string, or None.
    """
    if row.get("mcc") in known_mcc_codes(): # tier 1
        return row.get("mcc")

    key = merchant_key(row.get("raw_description")) # tier 2
    rule_mcc = _load_merchant_rules().get(key)
    if rule_mcc is not None:
        return rule_mcc

    # Tier 3/4: Redis + LLM — Phase 6 add later

    # Tier 5: Chase (or adapter) category text → canonical category →
    #         one representative MCC for that bucket.
    # Example: "Groceries" → "groceries" → "5411"
    #          "Fees & Adjustments" → "other" → None
    canonical = SOURCE_CATEGORY_MAP.get(row.get("source_category")) # tier 5
    if canonical is not None:
        return REPRESENTATIVE_MCC.get(canonical)

    # Tier 6: nothing matched
    return None