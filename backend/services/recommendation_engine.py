"""Recommendation engine."""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from apps.cards.models import Card_Products
from services.category_resolver import reward_categories, scoring_bucket

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")

SPARSE_TX_THRESHOLD = 5
LOW_COVERAGE_THRESHOLD = Decimal("70.0")
HIGH_COVERAGE_THRESHOLD = Decimal("90.0")
DISTORTION_THRESHOLD = Decimal("-200.00")

POINTS_CURRENCIES = {"points", "miles"}
DEFAULT_POINT_VALUE_CENTS = "1.0"


def point_value_cents() -> Decimal:
    """
    What one point or mile is worth, in cents.

    Points are a count, not money: a 75,000 point bonus is not $75,000. Every
    points figure passes through this before it can be compared against a
    dollar figure. One cent is the neutral default; set POINT_VALUE_CENTS in
    settings to value a transfer programme higher.
    """
    return Decimal(str(getattr(settings, "POINT_VALUE_CENTS", DEFAULT_POINT_VALUE_CENTS)))


def _earns_points(card) -> bool:
    return card.reward_currency in POINTS_CURRENCIES


def _rate_factor(card) -> Decimal:
    """Multiplier turning a published earn rate into an effective cash-back %."""
    return point_value_cents() if _earns_points(card) else Decimal("1")


def _bonus_in_dollars(card) -> Decimal:
    if _earns_points(card):
        return card.signup_bonus * point_value_cents() / _HUNDRED
    return card.signup_bonus


def _bonus_label(card) -> str:
    if _earns_points(card):
        return f"{card.signup_bonus:,.0f} {card.reward_currency}"
    return f"${card.signup_bonus}"


def _card_passes_gate(card, known_categories: frozenset) -> bool:
    if not card.name or not card.issuer or card.is_active is False:
        return False
    rules = list(card.reward_rules.all())

    if len(rules) == 0 and card.base_reward_rate == 0:
        return False # nothing to earn: no reward rules and no base rate
    for rule in rules:
        if rule.reward_rate <= 0:
            return False # a rule that earns nothing is bad catalog data
    return True


def get_valid_cards() -> list:
    known_categories = reward_categories()
    return [
        c for c in Card_Products.objects
            .filter(is_active=True, is_catalog=True)
            .prefetch_related("reward_rules")
        if _card_passes_gate(c, known_categories)
    ]


def fold_rules_to_buckets(card) -> dict[str, Decimal]:
    """
    Collapse the card's issuer-worded rules onto scoring buckets.

    Issuers name categories more finely than a bank statement can ("6% at US
    supermarkets", "5% on travel booked through the portal"), so several rules
    often land in one bucket. The highest rates are the conditional ones, so we
    keep the lowest: what you would earn on an ordinary charge in that bucket.
    Rules mapped to null are perks we cannot verify and are not scored.
    """
    folded: dict[str, Decimal] = {}
    for rule in card.reward_rules.all():
        bucket = scoring_bucket(rule.category)
        if bucket is None:
            continue
        current = folded.get(bucket)
        if current is None or rule.reward_rate < current:
            folded[bucket] = rule.reward_rate
    return folded


def score_card(card, annualized: dict, by_category: dict, months_covered: int) -> dict:
    """
    annualized -> spending_score; by_category -> signup bonus MUST NOT BE swapped.
    positive_actual excludes unresolved_amount.

    months_covered is statement-cycle evidence from the spend summary (per-upload
    ~30-day spans summed), not distinct calendar months of transaction_date.
    A mid-month billing cycle in one file counts as one month of data.
    """
    rule_map = fold_rules_to_buckets(card)
    rate_factor = _rate_factor(card)
    spending_score = ZERO
    annualized_total = ZERO
    explanation = []

    for cat, ann_spend in annualized.items():
        score_spend = max(ann_spend, ZERO)  # floor negatives
        annualized_total += score_spend
        rate = rule_map.get(cat, card.base_reward_rate)  # missing rule ->base
        effective_rate = rate * rate_factor  # published rate -> cash-back %
        value = score_spend * (effective_rate / _HUNDRED)
        spending_score += value
        explanation.append({
            "category": cat,
            "rate": str(rate),
            "effective_rate": str(effective_rate.quantize(CENTS, rounding=ROUND_HALF_UP)),
            "annualized_spend": str(score_spend.quantize(CENTS, rounding=ROUND_HALF_UP)),
            "value": str(value.quantize(CENTS, rounding=ROUND_HALF_UP)),
        })

    # the signup bonus
    period_months = card.signup_bonus_spend_period_months
    positive_actual = sum((max(v, ZERO) for v in by_category.values()), ZERO)

    if card.signup_bonus == 0:
        signup_bonus_score = ZERO
        signup_bonus_status = "no_bonus"
        signup_bonus_note = ""
        signup_bonus_detail: dict = {"status": "no_bonus"}
    elif positive_actual >= card.signup_bonus_required_spending:
        signup_bonus_score = _bonus_in_dollars(card)
        signup_bonus_status = "met"
        shown_actual = positive_actual.quantize(CENTS, rounding=ROUND_HALF_UP)
        signup_bonus_note = (
            f"Your spending of ${shown_actual} already clears the "
            f"${card.signup_bonus_required_spending} required"
            + (
                f" within {months_covered} month(s) of statements"
                if months_covered > 0
                else ""
            )
            + f" (card allows up to {period_months} months)."
        )
        signup_bonus_detail = {
            "status": "met",
            "positive_actual_spend": str(shown_actual),
            "required_spend": str(
                card.signup_bonus_required_spending.quantize(CENTS, rounding=ROUND_HALF_UP)
            ),
            "period_months": period_months,
            "months_of_data": months_covered,
            "met_early": months_covered < period_months,
        }
    elif months_covered < period_months:
        # Under the spend bar and not enough statement-months, ask for more uploads
        months_needed = period_months - months_covered
        signup_bonus_score = ZERO
        signup_bonus_status = "insufficient_data"
        signup_bonus_note = (
            f"Upload {months_needed} more month(s) of statements to evaluate this "
            f"card's {_bonus_label(card)} signup bonus, which needs "
            f"${card.signup_bonus_required_spending} of spend in {period_months} months."
        )
        signup_bonus_detail = {
            "status": "insufficient_data",
            "months_of_data": months_covered,
            "months_needed": months_needed,
            "period_months": period_months,
            "positive_actual_spend": str(
                positive_actual.quantize(CENTS, rounding=ROUND_HALF_UP)
            ),
            "required_spend": str(
                card.signup_bonus_required_spending.quantize(CENTS, rounding=ROUND_HALF_UP)
            ),
        }
    else:
        monthly_average = positive_actual / Decimal(months_covered)
        projected = monthly_average * Decimal(period_months)
        shown = projected.quantize(CENTS, rounding=ROUND_HALF_UP)
        if projected >= card.signup_bonus_required_spending:
            signup_bonus_score = _bonus_in_dollars(card)
            signup_bonus_status = "met"
            signup_bonus_note = (
                f"Your spending projects to ${shown} over {period_months} months, "
                f"clearing the ${card.signup_bonus_required_spending} required."
            )
        else:
            signup_bonus_score = ZERO
            signup_bonus_status = "not_met"
            signup_bonus_note = (
                f"Your spending projects to ${shown} over {period_months} months, "
                f"short of the ${card.signup_bonus_required_spending} required."
            )
        signup_bonus_detail = {
            "status": signup_bonus_status,
            "positive_actual_spend": str(
                positive_actual.quantize(CENTS, rounding=ROUND_HALF_UP)
            ),
            "monthly_average": str(monthly_average.quantize(CENTS, rounding=ROUND_HALF_UP)),
            "projected_spend": str(shown),
            "required_spend": str(
                card.signup_bonus_required_spending.quantize(CENTS, rounding=ROUND_HALF_UP)
            ),
            "period_months": period_months,
            "months_of_data": months_covered,
        }

    #  Total score
    total_score = spending_score - card.annual_fee + signup_bonus_score
    # What the card is worth every year after the one-time bonus stops applying.
    ongoing_annual_value = spending_score - card.annual_fee

    # Annual spend, at this user's category mix, that would make the fee pay for
    # itself. None when there is no fee, or when the card earns nothing at all.
    break_even_annual_spend = None
    if card.annual_fee > 0 and spending_score > 0:
        break_even_annual_spend = card.annual_fee * annualized_total / spending_score

    return {
        "card": card,
        "rule_map": rule_map,
        "spending_score": spending_score,
        "signup_bonus_score": signup_bonus_score,
        "signup_bonus_status": signup_bonus_status,
        "signup_bonus_note": signup_bonus_note,
        "signup_bonus_detail": signup_bonus_detail,
        "total_score": total_score,
        "ongoing_annual_value": ongoing_annual_value,
        "break_even_annual_spend": break_even_annual_spend,
        "annualized_total": annualized_total,
        "explanation": explanation,
    }


# the Tie-Breaker

def _rule_coverage(scored: dict, annualized: dict) -> int:
    """
    Count categories where the user has positive annualized spend AND the card
    has a specific reward rule. Base-rate coverage does not count — every card
    earns base on everything.
    """
    rule_cats = scored["rule_map"].keys()
    return sum(1 for cat, v in annualized.items() if v > ZERO and cat in rule_cats)


def _tie_key(scored: dict, annualized: dict) -> tuple:
    """
    Preference identity after all real tie-break tiers are exhausted.
    Equal _tie_key means equally good — the rank is shared between the tied cards
    """
    card = scored["card"]
    return (
        scored["total_score"],
        scored["spending_score"],
        _rule_coverage(scored, annualized),
        card.annual_fee,
        len(scored["rule_map"]),
    )


def _sort_key(scored: dict, annualized: dict) -> tuple:
    card = scored["card"]
    return (
        -scored["total_score"],
        -scored["spending_score"],
        -_rule_coverage(scored, annualized),
        card.annual_fee,
        len(scored["rule_map"]),
    )


def assign_competition_ranks(ordered: list[dict], annualized: dict) -> list[dict]:
    """Olympic ranks on a sorted list; mutates each dict with rank + rank_note."""
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
    scored_cards: list[dict], annualized: dict, limit: int = 5
) -> list[dict]:
    """
    Sort by preference tiers, take up to `limit` cards (arbitrary among residual
    ties at the cut), then attach competition ranks + rank_note.

    """
    ranked = sorted(scored_cards, key=lambda s: _sort_key(s, annualized))
    return assign_competition_ranks(ranked[:limit], annualized)


def compute_confidence(summary: dict) -> tuple[str, str]:
    """
    Returns (confidence, confidence_note)
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
