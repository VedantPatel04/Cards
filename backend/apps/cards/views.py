"""
Catalog endpoints — products that can be scored and added to a wallet.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cards.models import Card_Products


def _catalog_item(card: Card_Products) -> dict:
    return {
        "id": card.pk,
        "name": card.name,
        "issuer": card.issuer,
        "network": card.network,
        "card_type": card.card_type,
        "annual_fee": str(card.annual_fee),
        "base_reward_rate": str(card.base_reward_rate),
        "signup_bonus": str(card.signup_bonus),
        "signup_bonus_required_spending": str(card.signup_bonus_required_spending),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def catalog_list(request):
    """
    GET /api/cards/

    Shows all catalog products (is_catalog=True). Use these ids with POST /api/wallet/.
    """
    cards = (
        Card_Products.objects.filter(is_active=True, is_catalog=True).order_by("issuer", "name")
    )
    items = [_catalog_item(card) for card in cards]
    return Response({"count": len(items), "cards": items}, status=status.HTTP_200_OK)
