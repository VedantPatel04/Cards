"""
GET /api/recommendations/ — Stage 6 orchestrator.

Pipeline: spend summary → gate → score → select_top_cards → confidence → serialize.
"""

from decimal import ROUND_HALF_UP, Decimal

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from services.recommendation_engine import (
    compute_confidence,
    get_valid_cards,
    score_card,
    select_top_cards,
)
from services.spending_aggregator import get_spend_summary

CENTS = Decimal("0.01")


def _money(value) -> str:
    """Always two decimal places — same contract as /api/summary/."""
    return str((value or Decimal("0")).quantize(CENTS, rounding=ROUND_HALF_UP))


def _serialize(scored: dict) -> dict:
    """
    Format one select_top_cards row into the locked recommendation shape.
    Formatting only — no scoring math.
    """
    card = scored["card"]
    return {
        "rank": scored["rank"],
        "rank_note": scored["rank_note"],
        "card_id": card.pk,
        "card_name": card.name,
        "issuer": card.issuer,
        "spending_score": _money(scored["spending_score"]),
        "annual_fee": _money(card.annual_fee),
        "signup_bonus_score": _money(scored["signup_bonus_score"]),
        "signup_bonus_status": scored["signup_bonus_status"],
        "signup_bonus_note": scored["signup_bonus_note"],
        "total_score": _money(scored["total_score"]),
        "explanation": scored["explanation"],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommendations_view(request):
    """
    GET /api/recommendations/

    Authenticated. Uses request.user only — no body, no path params.
    recommendations length may be 0–3; ties share rank + rank_note.
    """
    summary = get_spend_summary(request.user)
    annualized = summary["annualized"]
    by_category = summary["by_category"]
    days_span = summary["period"]["days_span"]

    valid_cards = get_valid_cards()
    scored_cards = [
        score_card(card, annualized, by_category, days_span)
        for card in valid_cards
    ]
    top_cards = select_top_cards(scored_cards, annualized, limit=3)

    confidence, confidence_note = compute_confidence(summary)
    recommendations = [_serialize(scored) for scored in top_cards]

    return Response(
        {
            "confidence": confidence,
            "confidence_note": confidence_note,
            "recommendations": recommendations,
        },
        status=status.HTTP_200_OK,
    )
