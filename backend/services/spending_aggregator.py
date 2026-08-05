"""
Spend summary aggregation (recommendation pipeline Stage 1).

Public API: get_spend_summary(user) -> dict of Decimals (view serialises to strings).

Contracts:
- Net Sum(amount) per category; refunds reduce totals; negatives are not clamped.
- category="" excluded from by_category; reported as unresolved_count / unresolved_amount.
- All reward categories always present (even 0.00).
- annualized[c] = by_category[c] * 365 / days_span; days_span=0 only when no txs.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Max, Min, Sum

from apps.transactions.models import UNRESOLVED_CATEGORY, Transactions
from services.category_resolver import reward_categories

_ZERO = Decimal("0.00")
_CENTS = Decimal("0.01")
_ONE_DECIMAL = Decimal("0.1")
_365 = Decimal("365")


def _user_transactions(user):
    """All transactions belonging to this user, via their wallet cards."""
    return Transactions.objects.filter(user_card__user=user)


def get_spend_summary(user) -> dict:
    """Return the spend summary dict for user. See module docstring for full contract."""
    qs = _user_transactions(user)

    # Categorised net totals — seed all buckets so Day 6 never KeyErrors
    cats = sorted(reward_categories())
    by_category: dict[str, Decimal] = {c: _ZERO for c in cats}

    cat_rows = (
        qs.exclude(category=UNRESOLVED_CATEGORY)
        .values("category")
        .annotate(total=Sum("amount"))
    )
    for row in cat_rows:
        cat = row["category"]
        if cat in by_category:
            # is-not-None (not `or`) so a true zero total stays zero
            by_category[cat] = row["total"] if row["total"] is not None else _ZERO

    # Unresolved metadata
    unresolved_agg = qs.filter(category=UNRESOLVED_CATEGORY).aggregate(
        count=Count("id"), total=Sum("amount")
    )
    unresolved_count: int = unresolved_agg["count"] or 0
    unresolved_amount: Decimal = (
        unresolved_agg["total"]
        if unresolved_agg["total"] is not None
        else _ZERO
    )

    # Period
    period_agg = qs.aggregate(
        earliest=Min("transaction_date"),
        latest=Max("transaction_date"),
    )
    earliest = period_agg["earliest"]
    latest = period_agg["latest"]
    # Inclusive calendar days: same-day span is 1, not 0
    days_span = ((latest - earliest).days + 1) if (earliest and latest) else 0

    # Annualised estimates
    if days_span > 0:
        factor = _365 / Decimal(days_span)
        annualized: dict[str, Decimal] = {
            c: (v * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)
            for c, v in by_category.items()
        }
    else:
        annualized = {c: _ZERO for c in cats}

    # Derived totals
    total_spend: Decimal = sum(by_category.values(), _ZERO)
    total_count: int = qs.count()
    categorized_count = total_count - unresolved_count

    if total_count > 0:
        categorized_pct = (
            Decimal(categorized_count) / Decimal(total_count) * 100
        ).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)
    else:
        # Product choice: empty wallet = fully categorised (nothing left to resolve)
        categorized_pct = Decimal("100.0")

    return {
        "period": {
            "earliest": earliest,
            "latest": latest,
            "days_span": days_span,
        },
        "by_category": by_category,
        "annualized": annualized,
        "total_spend": total_spend,
        "transaction_count": total_count,
        "unresolved_count": unresolved_count,
        "unresolved_amount": unresolved_amount,
        "categorized_pct": categorized_pct,
    }
