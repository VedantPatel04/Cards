"""
Upload endpoint. Thin view: authenticate, hash the file for idempotency,
create/find the Uploads row, then hand the bytes to the pipeline service.
"""

import hashlib
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.uploads.models import Uploads
from apps.users.models import User_cards
from services.upload_pipeline import (
    STATUS_FAILED,
    STATUS_PENDING,
    process_upload,
)

logger = logging.getLogger(__name__)

# A credit-card statement is kilobytes. Anything larger is a mistake or an
# attack, and we reject it before spending memory or LLM budget on it.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_transactions(request):
    """
    POST /api/upload/  (multipart form-data: file=<csv>, user_card_id=<int>)

    Re-posting the same bytes is safe: the (user, file_hash) pair finds the
    existing Uploads row, and the pipeline's (upload, row_index) upsert
    refreshes those transactions instead of duplicating them.
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

    user_card_id = request.data.get("user_card_id")
    if not user_card_id:
        return Response(
            {"detail": "user_card_id is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Scoped to request.user: a valid id belonging to someone else must look
    # exactly like an id that does not exist.
    user_card = User_cards.objects.filter(
        pk=user_card_id, user=request.user, is_active=True
    ).first()
    if user_card is None:
        return Response(
            {"detail": "No active card in your wallet matches that user_card_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    file_bytes = uploaded_file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

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
        # Bad file, not a bad server: normalize_csv rejected the shape.
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
            "summary": summary,
        },
        status=status.HTTP_201_CREATED if was_created else status.HTTP_200_OK,
    )
