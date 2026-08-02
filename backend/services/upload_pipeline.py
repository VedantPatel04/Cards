"""
Upload orchestrator.

Ties the pieces together: adapter (csv_parser) -> resolver (mcc_resolver) ->
idempotent DB write of Transactions. Views stay thin and call process_upload.
"""

import logging

from django.conf import settings
from django.db import transaction

from apps.transactions.models import Transactions
from services.csv_parser import normalize_csv
from services.mcc_resolver import resolve_mcc
from services.merchant_normalize import merchant_key

logger = logging.getLogger(__name__)

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


def _resolution_key(row: dict) -> tuple[str, str, str, str]:
    """
    Identity of a resolution request: everything in the row that resolve_mcc()
    actually reads. Keying on merchant_key alone would make one Chase category
    win for a merchant that appears under two (e.g. AMAZON as both Shopping and
    Groceries), while still collapsing the six identical MTA rows into one call.
    """
    return (
        merchant_key(row.get("raw_description")),
        str(row.get("category") or ""),
        str(row.get("source_category") or ""),
        str(row.get("mcc") or ""),
    )


def process_upload(upload, user_card, file_bytes: bytes) -> dict:
    """
    Normalize a file, resolve MCCs, and persist Transactions idempotently.

    Resolution runs before the DB transaction opens: Tier 4 makes network calls
    to the LLM, and holding a Postgres transaction open across network I/O is a
    good way to create lock contention. Anything the resolver learns is written
    to MerchantResolution as it goes, so that work survives even if the
    Transactions write below fails.

    Returns a summary dict with keys:
      rows, merchants, created, updated, uncategorized, llm_calls

    llm_calls counts *attempts*, so a provider outage shows up as spent budget
    rather than as a silent retry storm.
    """
    rows = normalize_csv(file_bytes)

    # One shared budget for the whole upload (not per row).
    budget = UploadBudget(settings.LLM_MAX_CALLS_PER_UPLOAD)
    starting_budget = budget.remaining

    # Resolve each distinct merchant once, then reuse for duplicate rows
    # (e.g. six MTA lines → one resolve_mcc call).
    mcc_by_key: dict[tuple[str, str, str, str], str | None] = {}
    for row in rows:
        key = _resolution_key(row)
        if key not in mcc_by_key:
            mcc_by_key[key] = resolve_mcc(row, budget=budget)

    created = 0
    updated = 0
    uncategorized = 0
    with transaction.atomic():
        for row in rows:
            mcc = mcc_by_key[_resolution_key(row)]
            if mcc is None:
                uncategorized += 1
            _obj, was_created = Transactions.objects.update_or_create(
                upload=upload,
                row_index=row["row_index"],
                defaults={
                    "user_card": user_card,
                    "amount": row["amount"],
                    "transaction_date": row["transaction_date"],
                    "description": row["raw_description"],
                    "mcc_code_id": mcc,  # None is fine (nullable FK)
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        upload.status = STATUS_PROCESSED
        upload.save(update_fields=["status", "updated_at"])

    summary = {
        "rows": len(rows),
        "merchants": len(mcc_by_key),
        "created": created,
        "updated": updated,
        "uncategorized": uncategorized,  # rows stored with a NULL mcc_code
        "llm_calls": starting_budget - budget.remaining,
    }
    logger.info("upload %s processed: %s", upload.pk, summary)
    return summary
