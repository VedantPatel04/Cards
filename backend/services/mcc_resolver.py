"""
MCC resolver.

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

Every tier decision is logged at DEBUG under the "services.mcc_resolver"
logger, so `manage.py demo_upload` (or any log config) can show the ladder.
"""

import json
import logging
import os
from django.conf import settings
from services.csv_parser import CHASE_CATEGORY_MAP
from services.merchant_normalize import merchant_key
from services.merchant_cache import cache_get, cache_set
from apps.transactions.models import MCC_Codes, MerchantResolution

#llm_lookup_mcc imported inside Tier 4 to avoid circular import with known_mcc_codes

logger = logging.getLogger(__name__)

MERCHANT_RULES_PATH = os.path.join(
    settings.BASE_DIR, "data", "card_catalog", "merchant_rules.json"
)

# Tier 5 fallback CATEGORY MAP, "other" maps to None -> mcc_code stays NULL on the transaction.
REPRESENTATIVE_MCC = {
    "groceries": "5411",      # Grocery Stores and Supermarkets
    "dining": "5812",         # Eating Places and Restaurants (broadest sit-down)
    "travel": "4789",         # Transportation Services – Not Elsewhere Classified
    "gas": "5541",            # Service Stations
    "shopping": "5999",       # Miscellaneous and Specialty Retail Stores
    "entertainment": "7999",  # Recreation Services – Not Elsewhere Classified
    "other": None,
}

# Temporary alias for legacy rows using "source_category". Safe to remove once all rows have "category".
SOURCE_CATEGORY_MAP = CHASE_CATEGORY_MAP

# Confidence of llm lookup, rules and hardcoded information has a confidence level of 1.0
LLM_CONFIDENCE = 0.7

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
    """Load and memoize merchant_rules.json ({MERCHANT KEY: MCC})."""
    global merchant_rules
    if merchant_rules is None:
        with open(MERCHANT_RULES_PATH, "r") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError("merchant_rules.json must be a JSON object of key -> MCC")
        merchant_rules = loaded
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

    Returns a code that is guaranteed to exist in MCC_Codes, or None. That
    guarantee matters: Transactions.mcc_code is a FK, so returning a code the
    table doesn't have would fail the whole upload's write.
    """
    mcc = _resolve_tiers(row, budget)
    if mcc is not None and mcc not in known_mcc_codes():
        logger.warning(
            "discarding unknown MCC %r for %r (not in MCC_Codes)",
            mcc, row.get("raw_description"),
        )
        return None
    return mcc


def _resolve_tiers(row: dict, budget=None) -> str | None:
    """The tier ladder. Callers should use resolve_mcc(), which validates."""
    row_mcc = str(row.get("mcc") or "").strip()
    if row_mcc in known_mcc_codes():  # tier 1
        logger.debug("tier1 row-mcc %s for %r", row_mcc, row.get("raw_description")) # aids in logging when tier 1 resolves an MCC
        return row_mcc

    key = merchant_key(row.get("raw_description"))  # shared by tiers 2-4

    # An unusable description (digits/symbols only) normalizes to "". Every such
    # row would otherwise share one cache entry and one MerchantResolution row,
    # so skip straight to the category fallback.
    if not key:
        logger.debug("empty merchant key for %r, skipping tiers 2-4", row.get("raw_description"))
        return _tier5_category_fallback(row)

    rule_mcc = _load_merchant_rules().get(key)
    if rule_mcc is not None:  # tier 2
        logger.debug("tier2 rule hit %s -> %s", key, rule_mcc)
        return rule_mcc

    # Tier 3a — Redis L1. "" = known-unknown sentinel
    hit = cache_get(key)
    if hit is not None:
        logger.debug("tier3a cache hit %s -> %r", key, hit)
        return hit or None

    # Tier 3b — durable L2; warm up redis on a hit
    stored = MerchantResolution.objects.filter(merchant_key=key).first()
    if stored is not None:
        mcc = stored.mcc_code_id
        cache_set(key, mcc or "")
        logger.debug("tier3b db hit %s -> %r (redis warmed)", key, mcc)
        return mcc

    # Tier 4: LLM , if LLM is off/unkeyed we must NOT enter this branch
    llm_ready = bool(settings.LLM_ENABLED and settings.LLM_API_KEY)
    if budget is not None and budget.allows() and llm_ready:
        from services.llm_client import LLMUnavailable, llm_lookup_mcc

        try:
            mcc = llm_lookup_mcc(key)
        except LLMUnavailable:
            budget.spend()
            logger.warning("tier4 llm unavailable for %s, falling back to tier5", key)
            return _tier5_category_fallback(row) # calls our tier 5 fallback if LLM lookup returns with an error

        budget.spend()
        MerchantResolution.objects.update_or_create(
            merchant_key=key,
            defaults={
                "mcc_code_id": mcc,
                "category": _category_for(mcc),
                "source": "llm",
                "confidence": LLM_CONFIDENCE if mcc else 0.0,
            },
        )
        cache_set(key, mcc or "")
        logger.debug("tier4 llm %s -> %r (persisted + cached)", key, mcc)
        return mcc

    return _tier5_category_fallback(row)


def _category_for(mcc: str | None) -> str:
    """
    Denormalize the MCC's category onto the resolution row.

    Reward matching works in categories, not codes, so storing it here saves a
    join on the hot path. Only runs on a cold miss, so the extra query is rare.
    """
    if not mcc:
        return ""
    return (
        MCC_Codes.objects.filter(code=mcc)
        .values_list("category", flat=True)
        .first()
        or ""
    )


def _tier5_category_fallback(row: dict) -> str | None:
    """
    Tier 5 + Tier 6
    Example: "groceries" → "5411"
             "other" → None
    The adapter is what knows a provider's category words, so it hands us a
    canonical name. Rows built without one still work via the legacy Chase map.
    """
    canonical = row.get("category") or SOURCE_CATEGORY_MAP.get(row.get("source_category"))
    if canonical in REPRESENTATIVE_MCC:
        mcc = REPRESENTATIVE_MCC[canonical]
        logger.debug("tier5 category %r -> %r", canonical, mcc)
        return mcc

    logger.debug("tier6 unresolved %r", row.get("raw_description"))
    return None
