"""
Ingestion: parse CSV -> resolve categories -> save Transactions.

Speed tricks:
  1. If Walmart appears 40 times, look up its category once, not 40 times.
  2. Write all rows to the DB in few batched operations, not one query per row.
"""

from __future__ import annotations
import logging
from django.db import transaction

from apps.transactions.models import ENTRY_SPEND, UNRESOLVED_CATEGORY, Transactions
from services.category_resolver import ResolutionResult, resolve_category
from services.csv_parser import normalize_csv
from services.merchant_normalize import merchant_key, normalized_display

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_PROCESSED = "processed"

# Fields we write on both create and update.
_TX_WRITE_FIELDS = [
    "user_card",
    "amount",
    "transaction_date",
    "description",
    "normalized_description",
    "category",
    "merchant_key",
    "resolution_source",
    "confidence",
    "entry_type",
]


def _resolution_key(row: dict) -> tuple[str, str]:
    """
    Identity of a resolution: (merchant_key, adapter_category).

    Including the adapter category keeps a merchant that appears under two
    different bank categories as two distinct resolution calls, while still
    collapsing many identical rows into one.
    """
    return (
        merchant_key(row.get("raw_description")),
        str(row.get("category") or ""),
    )


def _build_tx_fields(row: dict, user_card, result: ResolutionResult) -> dict:
    return {
        "user_card": user_card,
        "amount": row["amount"],
        "transaction_date": row["transaction_date"],
        "description": row["raw_description"],
        "normalized_description": normalized_display(row.get("raw_description")),
        "category": result.category,
        "merchant_key": merchant_key(row.get("raw_description")),
        "resolution_source": result.source,
        "confidence": result.confidence,
        # Adapter must set entry_type ... default spend only if an older caller omitted it - should not happen for normalize_csv output
        "entry_type": row.get("entry_type") or ENTRY_SPEND,
    }


def ingest_transactions(upload, user_card, rows: list[dict]) -> dict:
    """
    Resolve categories and persist Transactions idempotently on
    (upload, row_index).

    Returns summary: rows, merchants, created, updated, needs_review,
    coverage_pct.
    """
    if not rows:
        raise ValueError("No transactions found in this file.")

    user_id = user_card.user_id

    # resolve once per unique key
    resolution_by_key: dict[tuple[str, str], ResolutionResult] = {}
    for row in rows:
        rkey = _resolution_key(row)
        if rkey not in resolution_by_key:
            resolution_by_key[rkey] = resolve_category(row, user_id)

    #fetch all transactions existing in db for this upload
    existing: dict[int, Transactions] = {
        tx.row_index: tx
        for tx in Transactions.objects.filter(upload=upload)
    }

    # create vs. update lists
    to_create: list[Transactions] = []
    to_update: list[Transactions] = []
    needs_review = 0

    for row in rows:
        rkey = _resolution_key(row)
        result = resolution_by_key[rkey]
        if result.category == UNRESOLVED_CATEGORY:
            needs_review += 1

        fields = _build_tx_fields(row, user_card, result)

        if row["row_index"] in existing:
            tx = existing[row["row_index"]]
            for k, v in fields.items():
                setattr(tx, k, v)
            to_update.append(tx)
        else:
            to_create.append(
                Transactions(upload=upload, row_index=row["row_index"], **fields)
            )

    with transaction.atomic():
        if to_create:
            Transactions.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            Transactions.objects.bulk_update(to_update, fields=_TX_WRITE_FIELDS, batch_size=500)
        upload.status = STATUS_PROCESSED
        upload.save(update_fields=["status", "updated_at"])

    resolved = len(rows) - needs_review
    coverage_pct = round(resolved / len(rows) * 100, 1)

    summary = {
        "rows": len(rows),
        "merchants": len(resolution_by_key),
        "created": len(to_create),
        "updated": len(to_update),
        "needs_review": needs_review,
        "coverage_pct": coverage_pct,
    }
    logger.info("upload %s ingested: %s", upload.pk, summary)
    return summary


def process_upload(upload, user_card, file_bytes: bytes) -> dict:
    """CSV entry point: normalize_csv -> ingest_transactions."""
    rows = normalize_csv(file_bytes)
    return ingest_transactions(upload, user_card, rows)
