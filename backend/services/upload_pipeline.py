"""
Phase 7 — Upload orchestrator.

Ties the pieces together: adapter (csv_parser) -> resolver (mcc_resolver) ->
idempotent DB write of Transactions. Views stay thin and call process_upload.
"""

from django.db import transaction

# TODO: wire these as you implement each phase
# from services.csv_parser import normalize_csv
# from services.mcc_resolver import resolve_mcc
# from services.merchant_normalize import merchant_key
# from apps.transactions.models import Transactions

# status constants we will use later
STATUS_PENDING = "pending"
STATUS_PROCESSED = "processed"
STATUS_FAILED = "failed"


class UploadBudget:
    """
    Per-upload cap on paid LLM calls. resolve_mcc() calls .allows() before a
    Tier 4 lookup and .spend() after one. Once `remaining` hits zero, unknown
    merchants fall through to the free category fallback (Tier 5).
    """

    def __init__(self, remaining: int):
        self.remaining = remaining

    def allows(self) -> bool:
        return self.remaining > 0

    def spend(self) -> None:
        if self.remaining > 0:
            self.remaining -= 1


@transaction.atomic
def process_upload(upload, user_card, file_bytes: bytes) -> dict:
    """
    Normalize a file, resolve MCCs, and persist Transactions idempotently.

    Steps to implement:
      1. rows = normalize_csv(file_bytes)
      2. Dedupe distinct merchant keys so each unknown is resolved ONCE
         (your 4 identical MTA rows should cost at most one LLM call).
      3. budget = UploadBudget(settings.LLM_MAX_CALLS_PER_UPLOAD)
      4. For each row: mcc = resolve_mcc(row, budget=budget), then
         update_or_create a Transactions keyed on (upload, row_index) so a
         re-run is a no-op (idempotent, like card_catalog_ingestion.py).
      5. Return a small summary dict (created/updated/llm_calls, etc.).

    Returns a summary dict.
    """
    # TODO: implement per docstring
    raise NotImplementedError
