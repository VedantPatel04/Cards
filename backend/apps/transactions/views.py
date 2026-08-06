"""
Review endpoints — the user-supplied side of categorization.

GET  /api/review/   what the pipeline could not categorize, grouped by merchant
POST /api/review/   save the user's answer and backfill their transactions

Everything here is scoped to request.user. A user can only see and label
merchants that appear in their own transactions.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction as db_transaction
from django.db.models import Count, Max, Sum
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.transactions.models import (
    SOURCE_USER,
    UNRESOLVED_CATEGORY,
    MerchantResolution,
    Transactions,
)
from services.category_resolver import is_valid_category, reward_categories
from services.merchant_cache import cache_set
from services.spending_aggregator import get_spend_summary

logger = logging.getLogger(__name__)

# One statement should not be able to open thousands of questions.
MAX_REVIEW_ITEMS = 200
MAX_TRANSACTION_ITEMS = 500

CENTS = Decimal("0.01")


def _user_transactions(user):
    """Every transaction belonging to a user, via the card it was spent on."""
    return Transactions.objects.filter(user_card__user=user)


def _money(value) -> str:
    """
    Always two decimal places.

    Aggregate scale is backend-dependent (Postgres keeps 25.00, SQLite returns
    25), and the API contract should not change with the database.
    """
    return str((value or Decimal("0")).quantize(CENTS, rounding=ROUND_HALF_UP))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transaction_list(request):
    """
    GET /api/transactions/

    This user's transactions, newest first. card_name / issuer are joined from
    the wallet -> catalog product; the FK (user_card_id) is kept for uploads.
    """
    rows = (
        _user_transactions(request.user)
        .select_related("user_card__card", "upload")
        .order_by("-transaction_date", "-id")[:MAX_TRANSACTION_ITEMS]
    )

    items = [
        {
            "id": row.pk,
            "upload_id": row.upload_id,
            "filename": row.upload.filename,
            "user_card_id": row.user_card_id,
            "card_name": row.user_card.card.name,
            "issuer": row.user_card.card.issuer,
            "transaction_date": row.transaction_date.isoformat(),
            "amount": _money(row.amount),
            "description": row.description,
            "normalized_description": row.normalized_description,
            "merchant_key": row.merchant_key,
            "category": row.category,
            "resolution_source": row.resolution_source,
            "confidence": row.confidence,
        }
        for row in rows
    ]

    return Response(
        {"count": len(items), "transactions": items},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def review_queue(request):
    """
    GET /api/review/

    Distinct merchants with at least one uncategorized transaction, largest
    total spend first — answering the top of this list moves the most dollars,
    so a user who answers three questions and stops still gets a useful result.
    """
    groups = (
        _user_transactions(request.user)
        .filter(category=UNRESOLVED_CATEGORY)
        .exclude(merchant_key="")
        .values("merchant_key")
        .annotate(
            transaction_count=Count("id"),
            total_amount=Sum("amount"),
            #normalized_description is identical across rows with the same merchant_key; Max() just picks one deterministically.
            display_name=Max("normalized_description"),
            #raw bank string: show as evidence below the clean name.
            sample_description=Max("description"),
        )
        .order_by("-total_amount")[:MAX_REVIEW_ITEMS]
    )

    items = [
        {
            "merchant_key": group["merchant_key"],
            "display_name": group["display_name"] or group["merchant_key"].title(),
            "sample_description": group["sample_description"],
            "transaction_count": group["transaction_count"],
            "total_amount": _money(group["total_amount"]),
        }
        for group in groups
    ]

    return Response(
        {
            "count": len(items),
            "categories": sorted(reward_categories()),
            "merchants": items,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_answer(request):
    """
    POST /api/review/  {"merchant_key": "TRADER JOES", "category": "groceries"}

    Saves the answer as this user's override and applies it to every one of
    their transactions for that merchant — including rows already categorized
    by the bank, because the user is the authority on their own spend.

    Re-posting is safe: the override is an upsert and the backfill is an UPDATE
    to a fixed value.
    """
    merchant_key = str(request.data.get("merchant_key") or "").strip()
    category = str(request.data.get("category") or "").strip()

    if not merchant_key:
        return Response(
            {"detail": "merchant_key is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_valid_category(category):
        return Response(
            {
                "detail": "category is not a known rewards category.",
                "categories": sorted(reward_categories()),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Requiring the merchant to exist in this user's own transactions makes a typo'd key a clear 404 instead of a silently useless row.
    owned = _user_transactions(request.user).filter(merchant_key=merchant_key)
    if not owned.exists():
        return Response(
            {"detail": "No transaction of yours matches that merchant_key."},
            status=status.HTTP_404_NOT_FOUND,
        )

    with db_transaction.atomic():
        MerchantResolution.objects.update_or_create(
            user=request.user,
            merchant_key=merchant_key,
            defaults={"category": category, "source": "user"},
        )
        # Count category flips separately from metadata stamping: a re-post of the
        # same category should still mark source=user / confidence=1.0 on every
        # owned row (bank/global labels are defaults, not final authority).
        category_changed = owned.exclude(category=category).count()
        owned.update(
            category=category,
            resolution_source=SOURCE_USER,
            confidence=1.0,
        )

    # After the commit, so a rolled-back write can never leave Redis serving a category the database does not have.
    cache_set(request.user.pk, merchant_key, category)

    logger.info(
        "user %s labeled %s as %s (%s category flips, all owned rows stamped user)",
        request.user.pk, merchant_key, category, category_changed,
    )

    return Response(
        {
            "merchant_key": merchant_key,
            "category": category,
            "transactions_updated": category_changed,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary_view(request):
    """
    GET /api/summary/

    All-time spend totals across all wallet cards, by rewards category.

    Returns net spend (refunds reduce category totals). Unresolved rows
    (category="") are excluded from by_category and reported separately in
    unresolved_count / unresolved_amount.

    All 7 category buckets are always present even if zero. Negative totals
    (e.g. other when card payments outweigh real spend) are not clamped —
    the Day 6 Confidence Check (Stage 5) handles distortion detection.

    The Day 6 recommendation engine calls get_spend_summary() directly as a
    service; this view serialises the same output for the HTTP API.
    """
    summary = get_spend_summary(request.user)
    period = summary["period"]

    return Response(
        {
            "period": {
                "earliest": period["earliest"].isoformat() if period["earliest"] else None,
                "latest": period["latest"].isoformat() if period["latest"] else None,
                "days_span": period["days_span"],
            },
            "by_category": {
                cat: _money(total)
                for cat, total in summary["by_category"].items()
            },
            "annualized": {
                cat: _money(total)
                for cat, total in summary["annualized"].items()
            },
            "total_spend": _money(summary["total_spend"]),
            "transaction_count": summary["transaction_count"],
            "unresolved_count": summary["unresolved_count"],
            "unresolved_amount": _money(summary["unresolved_amount"]),
            "categorized_pct": str(summary["categorized_pct"]),
        },
        status=status.HTTP_200_OK,
    )
