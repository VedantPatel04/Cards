"""
Recommendation engine — Stages 2–5.

Stage 1 (spend summary) lives in spending_aggregator.get_spend_summary.
Stage 6 (HTTP view + _serialize) wires these helpers together.
"""

from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from apps.cards.models import Card_Products
from services.category_resolver import reward_categories

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")

SPARSE_TX_THRESHOLD = 5
LOW_COVERAGE_THRESHOLD = Decimal("70.0")
HIGH_COVERAGE_THRESHOLD = Decimal("90.0")
DISTORTION_THRESHOLD = Decimal("-200.00")  # annualized "other" below this -> warn


def _card_passes_gate(card, known_categories: frozenset) -> bool:
    if not card.name or not card.issuer or card.is_active is False:
        return False  # card has no name, no issuer, or is inactive
    rules = list(card.reward_rules.all())

    if len(rules) == 0 and card.base_reward_rate == 0:
        return False # no reward rules or base reward rate
    for rule in rules:
        if rule.reward_rate <= 0:
            return False # rewarde rate cannot be negatgive
        if rule.category not in known_categories:
            return False
    return True


def get_valid_cards() -> list:
    known_categories = reward_categories()
    return [
        c for c in Card_Products.objects
            .filter(is_active=True, is_catalog=True)
            .prefetch_related("reward_rules")
        if _card_passes_gate(c, known_categories)
    ]


# score your card
def score_card(card, annualized:dict, by_category:dict, days_span:int) ->dict:
    """
    Score one card against spend inputs.

    annualized  → spending_score (projected annual)
    by_category → signup bonus check (actual observed net)
    Never swap those two dicts.

    Signup positive_actual uses categorised spend only — does NOT include
    summary["unresolved_amount"] (locked product choice).
    """
    #  the spendingscore
    rule_map = {rule.category: rule.reward_rate for rule in card.reward_rules.all()}
    spending_score = ZERO
    explanation = []

    for cat, ann_spend in annualized.items():
        score_spend = max(ann_spend, ZERO)  # floor negatives
        rate = rule_map.get(cat, card.base_reward_rate)  # missing rule ->base
        value = score_spend * (rate / _HUNDRED)
        spending_score += value
        explanation.append({
            "category": cat,
            "rate": str(rate),
            "annualized_spend": str(score_spend.quantize(CENTS, rounding=ROUND_HALF_UP)),
            "value": str(value.quantize(CENTS, rounding=ROUND_HALF_UP)),
        })

    # the signup bonus
    if card.signup_bonus == 0:
        signup_bonus_score = ZERO
        signup_bonus_status = "no_bonus"
        signup_bonus_note = ""
    else:
        bonus_period_days = card.signup_bonus_spend_period_months * 30
        if days_span == 0 or days_span < bonus_period_days:
            months_needed = ceil((bonus_period_days - days_span) / 30)
            signup_bonus_score = ZERO
            signup_bonus_status = "insufficient_data"
            signup_bonus_note = (
                f"Upload ~{months_needed} more month(s) of statements "
                f"to evaluate this card's ${card.signup_bonus} signup bonus."
            )
        else:
            positive_actual = sum((max(v, ZERO) for v in by_category.values()), ZERO)
            projected = positive_actual * Decimal(bonus_period_days) / Decimal(days_span)
            if projected >= card.signup_bonus_required_spending:
                signup_bonus_score = card.signup_bonus
                signup_bonus_status = "met"
                signup_bonus_note = ""
            else:
                signup_bonus_score = ZERO
                signup_bonus_status = "not_met"
                signup_bonus_note = ""

    #  Total score
    total_score = spending_score - card.annual_fee + signup_bonus_score
    return {
        "card": card,
        "spending_score": spending_score,
        "signup_bonus_score": signup_bonus_score,
        "signup_bonus_status": signup_bonus_status,
        "signup_bonus_note": signup_bonus_note,
        "total_score": total_score,
        "explanation": explanation,
    }


# the Tie-Breaker

def _rule_coverage(scored: dict, annualized: dict) -> int:
    """
    Count categories where the user has positive annualized spend AND the card
    has a specific reward rule. Base-rate coverage does not count — every card
    earns base on everything.
    """
    rule_cats = {rule.category for rule in scored["card"].reward_rules.all()}
    return sum(1 for cat, v in annualized.items() if v > ZERO and cat in rule_cats)


def _tie_key(scored: dict, annualized: dict) -> tuple:
    """
    Preference identity after all real tie-break tiers are exhausted.
    Equal _tie_key ⇒ equally good — shared competition rank (no name/id bias).
    """
    card = scored["card"]
    return (
        scored["total_score"],
        scored["spending_score"],
        _rule_coverage(scored, annualized),
        card.annual_fee,
        len(list(card.reward_rules.all())),
    )


def _sort_key(scored: dict, annualized: dict) -> tuple:
    """
    Ascending sort key — callers use sorted(..., key=_sort_key).
    Negatives flip score/coverage so higher wins; fee/rule-count stay ascending
    (lower fee / simpler card wins ties).

    No name/id finalizer: residual ties stay arbitrary in list order.
    Use select_top_cards() (or assign_competition_ranks) so ties share a rank.
    """
    card = scored["card"]
    return (
        -scored["total_score"],
        -scored["spending_score"],
        -_rule_coverage(scored, annualized),
        card.annual_fee,
        len(list(card.reward_rules.all())),  # prefetched — no DB hit
    )


def assign_competition_ranks(ordered: list[dict], annualized: dict) -> list[dict]:
    """
    Olympic / competition ranks on an already-sorted list:
    two cards tied for best → both rank 1; next distinct card → rank 3.

    Mutates each scored dict in place with:
      rank       — int
      rank_note  — non-empty when this card shares its rank with peers
    """
    i = 0
    n = len(ordered)
    while i < n:
        j = i + 1
        key_i = _tie_key(ordered[i], annualized)
        while j < n and _tie_key(ordered[j], annualized) == key_i:
            j += 1

        rank = i + 1  # 1-based index of the first card in this tied group
        group = ordered[i:j]
        names = [s["card"].name for s in group]
        tied = len(group) > 1

        for s in group:
            s["rank"] = rank
            if tied:
                others = [name for name in names if name != s["card"].name]
                s["rank_note"] = (
                    f"Tied with {', '.join(others)} — equally ranked; apply for any."
                )
            else:
                s["rank_note"] = ""
        i = j
    return ordered


def select_top_cards(
    scored_cards: list[dict], annualized: dict, limit: int = 3
) -> list[dict]:
    """
    Sort by preference tiers, take up to `limit` cards (arbitrary among residual
    ties at the cut), then attach competition ranks + rank_note.

    Hole: if more than `limit` cards share the boundary _tie_key, peers beyond
    `limit` are omitted with no "and N more" notice — product choice for MVP.
    """
    ranked = sorted(scored_cards, key=lambda s: _sort_key(s, annualized))
    return assign_competition_ranks(ranked[:limit], annualized)


# Confidence check

def compute_confidence(summary: dict) -> tuple[str, str]:
    """
    Returns (confidence, confidence_note).
    Order is intentional: sparse → low coverage → distortion → high → medium.
    """
    if summary["transaction_count"] < SPARSE_TX_THRESHOLD:
        return "low", "Too few transactions to score reliably."
    if summary["categorized_pct"] < LOW_COVERAGE_THRESHOLD:
        return "low", "Less than 70% of spend is categorised — clear the review queue first."
    other_ann = summary["annualized"].get("other", ZERO)
    if other_ann < DISTORTION_THRESHOLD:
        return "medium", "Large payment or credit rows may skew results."
    if summary["categorized_pct"] >= HIGH_COVERAGE_THRESHOLD:
        return "high", ""
    return "medium", "Some spend is uncategorised — results may improve after review."
