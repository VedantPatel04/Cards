"""
Upload endpoints.

POST /api/upload/     — ingest a Chase CSV onto one wallet card
GET  /api/uploads/    — list this user's statement imports
POST /api/uploads/<id>/reassign/ — move every transaction on that import
                                 to a different wallet card (wrong-card fix)

A statement always belongs to one user-owned card. Re-posting the same file
bytes refreshes row data only when the card matches. Switching cards requires
the explicit reassign endpoint — silent rebind on upload is rejected (409).
"""

import hashlib
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.transactions.models import Transactions
from apps.uploads.models import Uploads
from apps.users.models import User_cards
from services.upload_pipeline import STATUS_FAILED, STATUS_PENDING, process_upload

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _active_wallet_card(user, raw_id):
    """
    Resolve an active User_cards row owned by user.

    Returns (card, error_response). error_response is set on failure.
    """
    if raw_id is None or raw_id == "":
        return None, Response(
            {"detail": "user_card_id is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        card_id = int(raw_id)
    except (TypeError, ValueError):
        return None, Response(
            {"detail": "user_card_id must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    card = User_cards.objects.filter(
        pk=card_id, user=user, is_active=True
    ).select_related("card").first()
    if card is None:
        return None, Response(
            {"detail": "No active card in your wallet matches that user_card_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return card, None


def _upload_card_ids(upload) -> set[int]:
    return set(
        Transactions.objects.filter(upload=upload).values_list("user_card_id", flat=True)
    )


def _serialize_upload(upload: Uploads) -> dict:
    card_ids = list(_upload_card_ids(upload))
    # Invariant: one card per statement. If legacy data ever has more, surface it.
    primary_id = card_ids[0] if len(card_ids) == 1 else None
    card_name = issuer = None
    if primary_id is not None:
        entry = (
            User_cards.objects.select_related("card")
            .filter(pk=primary_id)
            .first()
        )
        if entry is not None:
            card_name = entry.card.name
            issuer = entry.card.issuer

    return {
        "upload_id": upload.pk,
        "filename": upload.filename,
        "status": upload.status,
        "transaction_count": Transactions.objects.filter(upload=upload).count(),
        "user_card_id": primary_id,
        "card_name": card_name,
        "issuer": issuer,
        "created_at": upload.created_at.isoformat(),
        "updated_at": upload.updated_at.isoformat(),
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_transactions(request):
    """
    POST /api/upload/  (multipart form-data: file=<csv>, user_card_id=<int>)

    Same bytes + same card → refresh rows (200).
    Same bytes + different card → 409; use reassign instead.
    """
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return Response(
            {"detail": "No file provided under the 'file' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        return Response(
            {"detail": f"File exceeds the {MAX_UPLOAD_BYTES} byte limit."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_card, err = _active_wallet_card(request.user, request.data.get("user_card_id"))
    if err is not None:
        return err

    file_bytes = uploaded_file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = Uploads.objects.filter(user=request.user, file_hash=file_hash).first()
    if existing is not None:
        bound = _upload_card_ids(existing)
        if bound and bound != {user_card.pk}:
            return Response(
                {
                    "detail": (
                        "This file was already imported under a different wallet card. "
                        "Reassign the upload instead of re-uploading."
                    ),
                    "upload_id": existing.pk,
                    "current_user_card_ids": sorted(bound),
                    "requested_user_card_id": user_card.pk,
                },
                status=status.HTTP_409_CONFLICT,
            )

    upload, was_created = Uploads.objects.update_or_create(
        user=request.user,
        file_hash=file_hash,
        defaults={
            "filename": uploaded_file.name[:255],
            "status": STATUS_PENDING,
        },
    )

    try:
        summary = process_upload(upload, user_card, file_bytes)
    except ValueError as exc:
        Uploads.objects.filter(pk=upload.pk).update(status=STATUS_FAILED)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        Uploads.objects.filter(pk=upload.pk).update(status=STATUS_FAILED)
        logger.exception("upload %s failed", upload.pk)
        return Response(
            {"detail": "Upload could not be processed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "upload_id": upload.pk,
            "filename": upload.filename,
            "status": upload.status,
            "user_card_id": user_card.pk,
            "summary": summary,
        },
        status=status.HTTP_201_CREATED if was_created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def upload_list(request):
    """GET /api/uploads/ — this user's statement imports, newest first."""
    uploads = Uploads.objects.filter(user=request.user).order_by("-created_at", "-id")
    items = [_serialize_upload(u) for u in uploads]
    return Response({"count": len(items), "uploads": items}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_reassign(request, upload_id: int):
    """
    POST /api/uploads/<upload_id>/reassign/  {"user_card_id": N}

    Moves every transaction on this import to another active wallet card.
    Use when a statement was attached to the wrong card.
    """
    upload = Uploads.objects.filter(pk=upload_id, user=request.user).first()
    if upload is None:
        return Response(
            {"detail": "No upload of yours matches that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    user_card, err = _active_wallet_card(request.user, request.data.get("user_card_id"))
    if err is not None:
        return err

    updated = Transactions.objects.filter(upload=upload).update(user_card=user_card)

    logger.info(
        "user %s reassigned upload %s → user_card %s (%s rows)",
        request.user.pk, upload.pk, user_card.pk, updated,
    )

    return Response(
        {
            "upload_id": upload.pk,
            "user_card_id": user_card.pk,
            "card_name": user_card.card.name,
            "issuer": user_card.card.issuer,
            "transactions_updated": updated,
        },
        status=status.HTTP_200_OK,
    )
