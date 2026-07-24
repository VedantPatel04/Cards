"""
Upload endpoint. Thin view: authenticate, hash the file for idempotency,
create/find the Uploads row, then hand the bytes to the pipeline service.
"""

import hashlib

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# TODO: wire these once implemented
# from apps.uploads.models import Uploads
# from services.upload_pipeline import process_upload, STATUS_PROCESSED, STATUS_FAILED


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_transactions(request):
    """
    POST /api/upload/  (multipart form-data, field name: "file")

    Steps to implement:
      1. Pull the uploaded file: request.FILES.get("file"); 400 if missing.
      2. file_bytes = f.read(); file_hash = sha256(file_bytes).hexdigest().
      3. update_or_create Uploads on (user=request.user, file_hash=...) so a
         re-upload of the same file is idempotent (matches the model's
         unique_together = ('user', 'file_hash')).
      4. Resolve which User_cards this upload belongs to (from request data).
      5. summary = process_upload(upload, user_card, file_bytes)
      6. Return the summary with an appropriate status code.

    Keep it thin — all real work lives in services/upload_pipeline.py.
    """
    # TODO: implement per docstring
    return Response(
        {"detail": "not implemented"},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )
