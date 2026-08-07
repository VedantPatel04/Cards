"""
Category resolver.

Maps a normalized transaction row to one of our rewards categories. The user
is the authority: their saved answer beats the bank's coarse category column
and the admin-curated global catalog.

Tier order (first match wins):
  1. Redis:              this user's cached answer
  2. MerchantResolution: this user's stored answer -> warm Redis
  3. GlobalMerchantAlias: admin-curated catalog
  4. Adapter category:   what the bank said, if it is in our vocabulary
  5. UNRESOLVED ("") -> surfaced to the user for review

Tier 5 deliberately does not guess "other". 

Rows with no merchant name at all are defaulted to "other" to avoid stranding them in the queue.

The global alias table is small (O(100) rows) and READ-ONLY during a request.
It is loaded into a module-level dict once per process to avoid a DB hit for
every distinct merchant in an upload. 

Call invalidate_global_alias_cache() after seeding new data.
"""

from __future__ import annotations
import json
import logging #for debugging babayy
import os
from typing import NamedTuple
from django.conf import settings

from apps.transactions.models import (
    SOURCE_BANK,
    SOURCE_GLOBAL,
    SOURCE_NONE,
    SOURCE_USER,
    UNRESOLVED_CATEGORY,
    GlobalMerchantAlias,
    MerchantResolution,
)
from services.merchant_cache import cache_get, cache_set
from services.merchant_normalize import merchant_key

logger = logging.getLogger(__name__)

REWARD_CATEGORIES_PATH = os.path.join(
    settings.BASE_DIR, "data", "card_catalog", "reward_categories.json"
)
REWARD_RULE_ALIASES_PATH = os.path.join(
    settings.BASE_DIR, "data", "card_catalog", "reward_rule_aliases.json"
)

_reward_categories: frozenset[str] | None = None
_reward_rule_aliases: dict[str, str | None] | None = None
_global_aliases: dict[str, tuple[str, str]] | None = None  # key -> (category, canonical_name)

def reward_categories() -> frozenset[str]:
    global _reward_categories
    if _reward_categories is None:
        with open(REWARD_CATEGORIES_PATH) as f:
            loaded = json.load(f)
        if not isinstance(loaded, list) or not all(isinstance(x, str) for x in loaded):
            raise ValueError("reward_categories.json must be a JSON array of strings")
        if not loaded:
            raise ValueError("reward_categories.json must not be empty")
        _reward_categories = frozenset(loaded)
    return _reward_categories


def is_valid_category(category: str) -> bool:
    return category in reward_categories()


def reward_rule_aliases() -> dict[str, str | None]:
    """
    Maps a card catalog's reward-rule label onto a scoring bucket.

    Issuers name categories far more finely than transactions can be labelled
    ("us_supermarkets", "prepaid_hotels_via_amex_travel"), so the catalog keeps
    the issuer's wording and this table folds it into the seven buckets that
    Transactions can actually produce.

    A value of null means "deliberately not scored" — rotating or
    activation-gated categories we cannot verify. Every label a catalog uses
    must appear here, so a typo fails ingestion instead of silently becoming a
    rule that can never match spend.
    """
    global _reward_rule_aliases
    if _reward_rule_aliases is None:
        with open(REWARD_RULE_ALIASES_PATH) as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("reward_rule_aliases.json must be a JSON object")
        known = reward_categories()
        for raw, bucket in loaded.items():
            if bucket is not None and bucket not in known:
                raise ValueError(
                    f"reward_rule_aliases.json maps '{raw}' to '{bucket}', "
                    f"which is not a rewards category"
                )
        _reward_rule_aliases = loaded
    return _reward_rule_aliases


def scoring_bucket(rule_category: str) -> str | None:
    """The bucket a reward rule scores against, or None if it is not scored."""
    return reward_rule_aliases().get(rule_category)


def _get_global_aliases() -> dict[str, tuple[str, str]]:
    """
    Returns {merchant_key: (category, canonical_name)} for all rows in
    GlobalMerchantAlias. Cached in this process; call
    invalidate_global_alias_cache() after writing new rows.
    """
    global _global_aliases
    if _global_aliases is None:
        _global_aliases = {
            row.merchant_key: (row.category, row.canonical_name)
            for row in GlobalMerchantAlias.objects.all()
        }
    return _global_aliases


def invalidate_global_alias_cache() -> None:
    """Drop the in-process alias cache so the next resolve re-reads from DB."""
    global _global_aliases
    _global_aliases = None

class ResolutionResult(NamedTuple):
    category: str
    source: str    #SOURCE_USER or SOURCE_GLOBAL or SOURCE_BANK or SOURCE_NONE
    confidence: float  # 1.0 or 0.9 or 0.7 or 0.0


UNRESOLVED_RESULT = ResolutionResult(
    category=UNRESOLVED_CATEGORY,
    source=SOURCE_NONE,
    confidence=0.0,
)

def resolve_category(row: dict, user_id: int) -> ResolutionResult:
    """
    Return the best category for one normalized row, plus the tier that
    produced it and a confidence score.

    The user_id is required: overrides are scoped per user, and so is the
    Redis key, so a stranger's answer cannot affect this user's results.
    """
    key = merchant_key(row.get("raw_description"))

    if key:
        # Tier 1 — user's cache answer (Redis)
        hit = cache_get(user_id, key)
        if hit is not None:
            if is_valid_category(hit):
                logger.debug("tier1 redis %s -> %s", key, hit)
                return ResolutionResult(hit, SOURCE_USER, 1.0)
            logger.debug("tier1 redis stale value %r for %s (ignored)", hit, key)

        # Tier 2 — user's stored override (Table MerchantResolution)
        stored = (
            MerchantResolution.objects
            .filter(user_id=user_id, merchant_key=key)
            .first()
        )
        if stored is not None and is_valid_category(stored.category):
            cache_set(user_id, key, stored.category)
            logger.debug("tier2 db %s -> %s (redis warmed)", key, stored.category)
            return ResolutionResult(stored.category, SOURCE_USER, 1.0)

        # Tier 3 — global table data
        aliases = _get_global_aliases()
        if key in aliases:
            cat, _ = aliases[key]
            if is_valid_category(cat):
                logger.debug("tier3 global %s -> %s", key, cat)
                return ResolutionResult(cat, SOURCE_GLOBAL, 0.9)

    # Tier 4 — the bank's labelled category
    candidate = str(row.get("category") or "").strip()
    if is_valid_category(candidate):
        logger.debug("tier4 bank %r -> %s", row.get("raw_description"), candidate)
        return ResolutionResult(candidate, SOURCE_BANK, 0.7)

    # Tier 5a — "other" (edge case i guess)
    if not key:
        logger.debug("unidentifiable merchant %r -> other", row.get("raw_description"))
        return ResolutionResult("other", SOURCE_NONE, 0.0)

    # Tier 5b — unidentifiable
    logger.debug("tier5 unresolved %r (needs user review)", row.get("raw_description"))
    return UNRESOLVED_RESULT
