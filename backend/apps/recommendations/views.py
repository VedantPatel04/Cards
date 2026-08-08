"""GET /api/recommendations/ """

from decimal import ROUND_HALF_UP, Decimal

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from services.recommendation_engine import (
    compute_confidence,
    get_valid_cards,
    point_value_cents,
    score_card,
    select_top_cards,
)
from services.spending_aggregator import get_spend_summary

CENTS = Decimal("0.01")
TOP_N = 5


def _money(value) -> str:
    """Always two decimal places same format as /api/summary/."""
    return str((value or Decimal("0")).quantize(CENTS, rounding=ROUND_HALF_UP))


def _headline(scored: dict) -> str:
    """One sentence a user can act on, in dollars rather than score points."""
    card = scored["card"]
    rewards = scored["spending_score"]
    ongoing = scored["ongoing_annual_value"]
    fee = card.annual_fee

    if fee == 0:
        return f"Earns about ${_money(rewards)} a year on your spending, with no annual fee."

    if ongoing >= 0:
        return (
            f"Earns about ${_money(rewards)} a year, which covers the ${_money(fee)} "
            f"annual fee and leaves ${_money(ongoing)}."
        )

    shortfall = _money(-ongoing)
    breakeven = scored["break_even_annual_spend"]
    if breakeven is None:
        return (
            f"The ${_money(fee)} annual fee outweighs the ${_money(rewards)} a year "
            f"this card earns on your spending — a net cost of ${shortfall} a year."
        )
    return (
        f"The ${_money(fee)} annual fee outweighs the ${_money(rewards)} a year this "
        f"card earns on your spending — a net cost of ${shortfall} a year. You would "
        f"need about ${_money(breakeven)} of annual spending at your current mix for "
        f"it to break even."
    )


def _serialize(scored: dict) -> dict:
    """
    Format one select_top_cards row into the fixed recommendation shape.
    Formatting only, no scoring math.
    """
    card = scored["card"]
    breakeven = scored["break_even_annual_spend"]
    item = {
        "rank": scored["rank"],
        "card_id": card.pk,
        "card_name": card.name,
        "issuer": card.issuer,
        "reward_currency": card.reward_currency,
        "headline": _headline(scored),
        "spending_score": _money(scored["spending_score"]),
        "annual_fee": _money(card.annual_fee),
        "signup_bonus_score": _money(scored["signup_bonus_score"]),
        "signup_bonus_status": scored["signup_bonus_status"],
        "signup_bonus_note": scored["signup_bonus_note"],
        "signup_bonus_detail": scored["signup_bonus_detail"],
        "total_score": _money(scored["total_score"]),
        "ongoing_annual_value": _money(scored["ongoing_annual_value"]),
        "break_even_annual_spend": None if breakeven is None else _money(breakeven),
        "explanation": scored["explanation"],
    }
    # Only present when this card actually ties with another, so clients never
    # render an empty column.
    if scored["rank_note"]:
        item["rank_note"] = scored["rank_note"]
    return item


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommendations_view(request):
    """
    GET /api/recommendations/

    Authenticated. Uses request.user only — no body, no path params.
    recommendations length may be 0–5; ties share a rank and carry rank_note.
    """
    summary = get_spend_summary(request.user)
    annualized = summary["annualized"]
    by_category = summary["by_category"]
    months_covered = summary["period"]["months_covered"]

    valid_cards = get_valid_cards()
    scored_cards = [
        score_card(card, annualized, by_category, months_covered)
        for card in valid_cards
    ]
    top_cards = select_top_cards(scored_cards, annualized, limit=TOP_N)

    confidence, confidence_note = compute_confidence(summary)
    recommendations = [_serialize(scored) for scored in top_cards]

    return Response(
        {
            "confidence": confidence,
            "confidence_note": confidence_note,
            "value_basis": {
                "currency": "usd",
                "period": "per_year",
                "months_of_data": months_covered,
                "point_value_cents": str(point_value_cents()),
                "note": (
                    "Money fields are estimated US dollars. total_score is first-year "
                    "value including the signup bonus; ongoing_annual_value excludes it."
                ),
            },
            "recommendations": recommendations,
        },
        status=status.HTTP_200_OK,
    )
