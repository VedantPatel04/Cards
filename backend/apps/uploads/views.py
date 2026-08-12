"""
Upload endpoints.

POST /api/upload/     — ingest one or more Chase CSVs onto one wallet card
GET  /api/uploads/    — list this user's statement imports
POST /api/uploads/<id>/reassign/ — move every transaction on that import
                                 to a different wallet card (wrong-card fix)
DELETE /api/uploads/<id>/ — hard-delete a statement import (and its rows)

Failed ingests do not leave status=failed shells: the Uploads row is deleted
unless it already has transactions, in which case status is restored to processed.

A statement always belongs to one user-owned card. Re-posting the same file
bytes refreshes row data only when the card matches. Switching cards requires
the explicit reassign endpoint — and a silent rebind on upload is rejected (409).
"""

import hashlib
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from apps.transactions.models import Transactions
from apps.uploads.models import Uploads
from apps.users.models import User_cards
from config.api_schema import UploadCreateSerializer, UploadReassignSerializer
from services.upload_pipeline import STATUS_PENDING, STATUS_PROCESSED, process_upload

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


def _collect_upload_files(request):
    """
    Gather uploaded CSVs from multipart form-data.

    Accepts repeated `file` keys and/or repeated `files` keys
    (Postman multi-select / curl -F file=@a -F file=@b).
    """
    files = list(request.FILES.getlist("file")) + list(request.FILES.getlist("files"))
    # Preserve order; drop accidental empties.
    return [f for f in files if f is not None]


def _abandon_failed_upload(upload: Uploads) -> int | None:
    """
    Drop a failed import shell. If the row already has transactions (re-upload
    of bytes that previously succeeded, then failed on a later parse), keep the
    row and restore status to processed so we do not cascade-delete good data.
    """
    if Transactions.objects.filter(upload=upload).exists():
        Uploads.objects.filter(pk=upload.pk).update(status=STATUS_PROCESSED)
        return upload.pk
    upload_id = upload.pk
    upload.delete()
    return None


def _ingest_one_file(user, uploaded_file, user_card):
    """
    Ingest a single CSV onto user_card.

    Returns (payload_dict, http_status). payload always includes filename;
    failures include detail (and conflict fields when applicable).
    """
    filename = (uploaded_file.name or "upload.csv")[:255]

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        return (
            {
                "ok": False,
                "filename": filename,
                "detail": f"File exceeds the {MAX_UPLOAD_BYTES} byte limit.",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    file_bytes = uploaded_file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = Uploads.objects.filter(user=user, file_hash=file_hash).first()
    if existing is not None:
        bound = _upload_card_ids(existing)
        if bound and bound != {user_card.pk}:
            return (
                {
                    "ok": False,
                    "filename": filename,
                    "detail": (
                        "This file was already imported under a different wallet card. "
                        "Reassign the upload instead of re-uploading."
                    ),
                    "upload_id": existing.pk,
                    "current_user_card_ids": sorted(bound),
                    "requested_user_card_id": user_card.pk,
                },
                status.HTTP_409_CONFLICT,
            )

    upload, was_created = Uploads.objects.update_or_create(
        user=user,
        file_hash=file_hash,
        defaults={
            "filename": filename,
            "status": STATUS_PENDING,
        },
    )

    try:
        summary = process_upload(upload, user_card, file_bytes)
    except ValueError as exc:
        kept_id = _abandon_failed_upload(upload)
        body = {"ok": False, "filename": filename, "detail": str(exc)}
        if kept_id is not None:
            body["upload_id"] = kept_id
        return body, status.HTTP_400_BAD_REQUEST
    except Exception:
        kept_id = _abandon_failed_upload(upload)
        logger.exception("upload %s failed", kept_id or "(deleted)")
        body = {
            "ok": False,
            "filename": filename,
            "detail": "Upload could not be processed.",
        }
        if kept_id is not None:
            body["upload_id"] = kept_id
        return body, status.HTTP_500_INTERNAL_SERVER_ERROR

    http_status = status.HTTP_201_CREATED if was_created else status.HTTP_200_OK
    return (
        {
            "ok": True,
            "upload_id": upload.pk,
            "filename": upload.filename,
            "status": upload.status,
            "user_card_id": user_card.pk,
            "summary": summary,
        },
        http_status,
    )


@extend_schema(
    request=UploadCreateSerializer,
    responses={200: dict, 201: dict, 207: dict, 400: dict, 409: dict},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_transactions(request):
    """
    POST /api/upload/  (multipart: file|files=<csv>+, user_card_id=<int>)

    One file → same response shape as before (no batch wrapper).
    Multiple files → {count, succeeded, failed, results[]} with per-file ok/detail.
    Same bytes + same card → refresh rows (200).
    Same bytes + different card → 409; use reassign instead.
    """
    uploaded_files = _collect_upload_files(request)
    if not uploaded_files:
        return Response(
            {"detail": "No file provided under the 'file' (or 'files') field."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_card, err = _active_wallet_card(request.user, request.data.get("user_card_id"))
    if err is not None:
        return err

    if len(uploaded_files) == 1:
        payload, http_status = _ingest_one_file(
            request.user, uploaded_files[0], user_card
        )
        # Single-file responses stay backward-compatible (no ok wrapper).
        body = {k: v for k, v in payload.items() if k != "ok"}
        return Response(body, status=http_status)

    results = []
    succeeded = failed = 0
    any_created = False
    for uploaded_file in uploaded_files:
        payload, http_status = _ingest_one_file(request.user, uploaded_file, user_card)
        item = {**payload, "http_status": http_status}
        results.append(item)
        if payload.get("ok"):
            succeeded += 1
            if http_status == status.HTTP_201_CREATED:
                any_created = True
        else:
            failed += 1

    body = {
        "count": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
    if failed == 0:
        overall = status.HTTP_201_CREATED if any_created else status.HTTP_200_OK
    elif succeeded == 0:
        overall = status.HTTP_400_BAD_REQUEST
    else:
        overall = status.HTTP_207_MULTI_STATUS
    return Response(body, status=overall)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def upload_list(request):
    """GET /api/uploads/ — this user's statement imports, newest first."""
    uploads = Uploads.objects.filter(user=request.user).order_by("-created_at", "-id")
    items = [_serialize_upload(u) for u in uploads]
    return Response({"count": len(items), "uploads": items}, status=status.HTTP_200_OK)


@extend_schema(request=UploadReassignSerializer, responses={200: dict, 400: dict, 404: dict})
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


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def upload_delete(request, upload_id: int):
    """
    DELETE /api/uploads/<upload_id>/

    Hard-deletes this user's statement import. Related transactions cascade.
    """
    upload = Uploads.objects.filter(pk=upload_id, user=request.user).first()
    if upload is None:
        return Response(
            {"detail": "No upload of yours matches that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    upload_pk = upload.pk
    upload.delete()
    logger.info("user %s deleted upload %s", request.user.pk, upload_pk)
    return Response(status=status.HTTP_204_NO_CONTENT)
