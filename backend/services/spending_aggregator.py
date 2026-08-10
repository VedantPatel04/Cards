"""
Spend summary aggregation (recommendation pipeline Stage 1).

Public API: get_spend_summary(user) -> dict of Decimals (view serialises to strings).

Contracts:
- Only entry_type spend + refund feed by_category / total_spend.
  Refunds (negative amounts) reduce the category total.
  Payment and adjustment rows stay on the ledger but are excluded from spend math
  (bill payments and statement credits are not purchases).
- category="" excluded from by_category; reported as unresolved_count / unresolved_amount
  (unresolved counts only spend + refund rows).
- All reward categories always present (even 0.00).
- annualized[c] = by_category[c] * 12 / months_covered; 0.00 when no txs.
- months_covered is statement-cycle evidence: for each upload,
  max(1, round(inclusive_span_days / 30)), then sum across uploads.
  Mid-month billing cycles and calendar spillover do not invent extra months.
  Empty gaps between separate uploads are not counted (unlike global days_span).
- months_breakdown remains distinct calendar months (display / debugging only).
- transaction_count / months_breakdown / days_span include ALL ledger rows
  (including payments).
- days_span is reported for display but must not be used to extrapolate.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncMonth

from apps.transactions.models import (
    SPEND_SUMMARY_ENTRY_TYPES,
    UNRESOLVED_CATEGORY,
    Transactions,
)
from services.category_resolver import reward_categories

_ZERO = Decimal("0.00")
_CENTS = Decimal("0.01")
_ONE_DECIMAL = Decimal("0.1")
_MONTHS_PER_YEAR = Decimal("12")
_DAYS_PER_STATEMENT_MONTH = 30


def _user_transactions(user):
    """All transactions belonging to this user, via their wallet cards."""
    return Transactions.objects.filter(user_card__user=user)


def _statement_months_for_span(earliest, latest) -> int:
    """
    How many ~30-day statement cycles one upload's date span represents.

    Inclusive day count so a single-day file is 1 day → max(1, round(1/30)) = 1.
    A typical mid-month cycle (~30 inclusive days) stays 1, not 2 calendar months.
    """
    if earliest is None or latest is None:
        return 0
    span_days = (latest - earliest).days + 1
    return max(1, round(span_days / _DAYS_PER_STATEMENT_MONTH))


def _months_covered_from_uploads(qs) -> int:
    """Sum per-upload statement months. Empty ledger → 0."""
    spans = qs.values("upload_id").annotate(
        earliest=Min("transaction_date"),
        latest=Max("transaction_date"),
    )
    return sum(
        _statement_months_for_span(row["earliest"], row["latest"]) for row in spans
    )


def get_spend_summary(user) -> dict:
    """Return the spend summary dict for user. See module docstring for full contract."""
    qs = _user_transactions(user)
    spend_qs = qs.filter(entry_type__in=SPEND_SUMMARY_ENTRY_TYPES)

    # Categorised net totals — seed all buckets so Day 6 never KeyErrors
    cats = sorted(reward_categories())
    by_category: dict[str, Decimal] = {c: _ZERO for c in cats}

    cat_rows = (
        spend_qs.exclude(category=UNRESOLVED_CATEGORY)
        .values("category")
        .annotate(total=Sum("amount"))
    )
    for row in cat_rows:
        cat = row["category"]
        if cat in by_category:
            # is-not-None (not `or`) so a true zero total stays zero
            by_category[cat] = row["total"] if row["total"] is not None else _ZERO

    # Unresolved metadata (purchase/refund rows only — not bill payments)
    unresolved_agg = spend_qs.filter(category=UNRESOLVED_CATEGORY).aggregate(
        count=Count("id"), total=Sum("amount")
    )
    unresolved_count: int = unresolved_agg["count"] or 0
    unresolved_amount: Decimal = (
        unresolved_agg["total"]
        if unresolved_agg["total"] is not None
        else _ZERO
    )

    # Period dates — full ledger
    period_agg = qs.aggregate(
        earliest=Min("transaction_date"),
        latest=Max("transaction_date"),
    )
    earliest = period_agg["earliest"]
    latest = period_agg["latest"]
    # Inclusive calendar days: same-day span is 1, not 0. Descriptive only.
    days_span = ((latest - earliest).days + 1) if (earliest and latest) else 0

    # Calendar-month histogram for display — not the extrapolation base.
    _month_rows = (
        qs.annotate(_m=TruncMonth("transaction_date"))
        .values("_m")
        .annotate(transaction_count=Count("id"))
        .order_by("_m")
    )
    months_breakdown = [
        {"month": row["_m"].strftime("%Y-%m"), "transaction_count": row["transaction_count"]}
        for row in _month_rows
    ]

    # Statement-cycle evidence (signup + annualize use this, not len(breakdown)).
    months_covered: int = _months_covered_from_uploads(qs)

    # Annualised estimates
    if months_covered > 0:
        factor = _MONTHS_PER_YEAR / Decimal(months_covered)
        annualized: dict[str, Decimal] = {
            c: (v * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)
            for c, v in by_category.items()
        }
    else:
        annualized = {c: _ZERO for c in cats}

    # Derived totals
    total_spend: Decimal = sum(by_category.values(), _ZERO)
    total_count: int = qs.count()
    categorized_count = total_count - qs.filter(category=UNRESOLVED_CATEGORY).count()

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
            "months_covered": months_covered,
            "months_breakdown": months_breakdown,
        },
        "by_category": by_category,
        "annualized": annualized,
        "total_spend": total_spend,
        "transaction_count": total_count,
        "unresolved_count": unresolved_count,
        "unresolved_amount": unresolved_amount,
        "categorized_pct": categorized_pct,
    }
