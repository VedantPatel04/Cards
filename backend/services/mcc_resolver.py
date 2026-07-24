"""
Phases 2 & 6 — Tiered merchant -> MCC resolver.

Takes an already-normalized row (produced by the CSV adapter) and returns an
MCC code that exists in MCC_Codes, or None. The adapter decides the file
format; this file decides categorization, so nothing here is Chase-specific.

Tier order:
  1. MCC already on the row (synthetic CSV)           free
  2. merchant_rules.json keyword match                free
  3. Redis GET -> MerchantResolution DB row           free (cache hit)
  4. LLM call (only if budget remains) -> write both  paid, once per merchant
  5. source_category -> representative MCC            free
  6. None                                             free
"""

import json
import os

from django.conf import settings

# TODO: import the pieces you'll need as you build each tier
# from services.merchant_normalize import merchant_key
# from services.merchant_cache import cache_get, cache_set
# from services.llm_client import llm_lookup_mcc
# from apps.transactions.models import MCC_Codes, MerchantResolution

MERCHANT_RULES_PATH = os.path.join(
    settings.BASE_DIR, "data", "card_catalog", "merchant_rules.json"
)

# category -> one representative MCC used for the fuzzy Tier 5 fallback.
# TODO: fill from mcc_category_map.json (pick a generic code per category).
REPRESENTATIVE_MCC = {
    # "groceries": "5411",
    # "dining": "5812",
    # "travel": "4121",
    # "gas": "5541",
    # "shopping": "5999",
    # "entertainment": "7999",
    # "other": None,
}

# adapter-specific text category -> canonical category (Chase example).
# TODO: move to the adapter if you add more sources.
SOURCE_CATEGORY_MAP = {
    # "Groceries": "groceries",
    # "Food & Drink": "dining",
    # "Travel": "travel",
    # "Shopping": "shopping",
    # "Fees & Adjustments": "other",
}


def known_mcc_codes() -> set[str]:
    """
    Return the set of valid MCC codes (from MCC_Codes). Used by Tier 1 and to
    validate LLM output. Cache in a module-level variable so it's queried once.
    """
    # TODO: MCC_Codes.objects.values_list("code", flat=True) -> set, memoized
    raise NotImplementedError


def _load_merchant_rules() -> dict:
    """Load and memoize merchant_rules.json ({KEYWORD: MCC})."""
    # TODO: read MERCHANT_RULES_PATH once, cache in a module-level variable
    raise NotImplementedError


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
    # Tier 1: row.get("mcc") if it is a real known code
    # Tier 2: _load_merchant_rules().get(merchant_key(row["raw_description"]))
    # Tier 3: cache_get -> MerchantResolution row (warm cache on DB hit)
    # Tier 4: if budget and budget.allows(): llm_lookup_mcc(...) then persist
    #         to MerchantResolution + cache_set
    # Tier 5: REPRESENTATIVE_MCC[SOURCE_CATEGORY_MAP.get(source_category)]
    # Tier 6: return None
    # TODO: implement the tiers in order
    raise NotImplementedError
