"""
Wallet endpoints — cards this user owns (User_cards rows).

POST accepts either:
  { "card_product_id": N }                         — add from catalog
  { "name", "issuer", "network" }                  — custom / free-text card

Custom cards are user-scoped (Card_Products.owner). Name+issuer matching:
  1. Active catalog product (shared) → attach
  2. This user's own custom product → attach
  3. Else create a new custom row owned by this user

Never attach another user's custom Card_Products row.

DELETE is a hard delete: Transactions cascade with the wallet row. Statement
imports (Uploads) left with zero transactions for this user are removed too.
If the product was custom and owned by this user with no remaining wallet
refs, the orphan Card_Products row is deleted as well.

Card_Products.is_active still matters for catalog lifecycle (ingest soft-
deactivates removed snapshot products). Inactive products cannot be added.
User_cards.is_active is largely vestigial under hard-delete but still filtered
on list/upload until a later cleanup.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Count
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cards.models import Card_Products
from apps.uploads.models import Uploads
from apps.users.models import User_cards
from config.api_schema import WalletCreateSerializer

_ZERO = Decimal("0.00")


def _wallet_item(entry: User_cards) -> dict:
    card = entry.card
    return {
        "id": entry.pk,  # this is user_card_id for /api/upload/
        "card_product_id": card.pk,
        "card_name": card.name,
        "issuer": card.issuer,
        "network": card.network,
        "is_catalog": card.is_catalog,
        "is_active": entry.is_active,
    }


@extend_schema_view(
    get=extend_schema(
        responses={200: dict},
        description="List active wallet cards for the signed-in user.",
    ),
    post=extend_schema(
        request=WalletCreateSerializer,
        responses={201: dict, 400: dict},
        description=(
            "Add a catalog card by product id, or a custom card by "
            "name, issuer, and network."
        ),
    ),
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def wallet_list_or_add(request):
    if request.method == "GET":
        return _wallet_list(request)
    return _wallet_add(request)


def _wallet_list(request):
    """GET /api/wallet/ — active wallet entries for this user."""
    entries = (
        User_cards.objects.filter(user=request.user, is_active=True)
        .select_related("card")
        .order_by("card__issuer", "card__name")
    )
    items = [_wallet_item(entry) for entry in entries]
    return Response({"count": len(items), "cards": items}, status=status.HTTP_200_OK)


def _attach_card(user, card: Card_Products):
    """Create wallet row or 400 if this user already owns the product."""
    if not card.is_active:
        return Response(
            {"detail": "That card is inactive and cannot be added to your wallet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User_cards.objects.filter(user=user, card=card).exists():
        return Response(
            {"detail": "That card already exists in your wallet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        entry = User_cards.objects.create(user=user, card=card, is_active=True)
    except IntegrityError:
        # Race: concurrent request added the same card between the exists() check and create().
        return Response(
            {"detail": "That card already exists in your wallet."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(_wallet_item(entry), status=status.HTTP_201_CREATED)


def _wallet_add_by_product_id(request, raw_id):
    try:
        card_product_id = int(raw_id)
    except (TypeError, ValueError):
        return Response(
            {"detail": "card_product_id must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Add-by-id is the catalog picker path: must be an active catalog product.
    card = Card_Products.objects.filter(
        pk=card_product_id, is_active=True, is_catalog=True, owner__isnull=True
    ).first()
    if card is None:
        return Response(
            {"detail": "No active catalog card matches that card_product_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return _attach_card(request.user, card)


def _wallet_add_custom(request):
    name = str(request.data.get("name") or "").strip()
    issuer = str(request.data.get("issuer") or "").strip()
    network = str(request.data.get("network") or "").strip()
    user = request.user

    missing = [
        field
        for field, value in (("name", name), ("issuer", issuer), ("network", network))
        if not value
    ]
    if missing:
        return Response(
            {"detail": f"Missing required fields: {', '.join(missing)}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Prefer an active catalog product with this name+issuer (shared intentionally).
    catalog = Card_Products.objects.filter(
        name__iexact=name,
        issuer__iexact=issuer,
        is_catalog=True,
        is_active=True,
        owner__isnull=True,
    ).first()
    if catalog is not None:
        return _attach_card(user, catalog)

    # Otherwise only this user's own custom product — never another tenant's.
    existing = Card_Products.objects.filter(
        name__iexact=name,
        issuer__iexact=issuer,
        is_catalog=False,
        owner=user,
    ).first()
    if existing is not None:
        return _attach_card(user, existing)

    try:
        card = Card_Products.objects.create(
            name=name,
            issuer=issuer,
            network=network,
            card_type="credit",
            is_active=True,
            is_catalog=False,
            owner=user,
            annual_fee=_ZERO,
            base_reward_rate=_ZERO,
            signup_bonus=_ZERO,
            signup_bonus_required_spending=_ZERO,
        )
    except IntegrityError:
        # Race: concurrent create of the same owned custom.
        card = Card_Products.objects.filter(
            name__iexact=name,
            issuer__iexact=issuer,
            is_catalog=False,
            owner=user,
        ).first()
        if card is None:
            return Response(
                {"detail": "A conflict occurred creating that card. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    return _attach_card(user, card)


def _wallet_add(request):
    """
    POST /api/wallet/

      {"card_product_id": N}
      {"name": "...", "issuer": "...", "network": "..."}
    """
    raw_id = request.data.get("card_product_id")
    if raw_id is not None and raw_id != "":
        return _wallet_add_by_product_id(request, raw_id)

    has_any_custom = any(
        request.data.get(key) not in (None, "")
        for key in ("name", "issuer", "network")
    )
    if has_any_custom:
        return _wallet_add_custom(request)

    return Response(
        {
            "detail": (
                "Provide card_product_id (catalog) or name, issuer, and network (custom)."
            ),
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def wallet_delete(request, wallet_id: int):
    """Remove a wallet card and its related transactions."""
    entry = (
        User_cards.objects.select_related("card")
        .filter(pk=wallet_id, user=request.user)
        .first()
    )
    if entry is None:
        return Response(
            {"detail": "No wallet entry of yours matches that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    card = entry.card
    with db_transaction.atomic():
        entry.delete()
        if (
            not card.is_catalog
            and card.owner_id == request.user.pk
            and not User_cards.objects.filter(card_id=card.pk).exists()
        ):
            card.delete()

        # Uploads are not FK'd to the wallet card — only transactions are.
        # After the cascade, drop statement shells left with no rows.
        (
            Uploads.objects.filter(user=request.user)
            .annotate(tx_count=Count("upload_transactions"))
            .filter(tx_count=0)
            .delete()
        )

    return Response(status=status.HTTP_204_NO_CONTENT)
