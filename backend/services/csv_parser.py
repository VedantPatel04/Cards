"""
Phase 7 — CSV adapter.

The ONLY place that knows a specific bank's column names. Its job is to turn
raw file bytes into a list of normalized row dicts that the pipeline and
resolver understand. Add one function per source (Chase now, Plaid later) and
nothing downstream changes.
"""

import csv
import io


def normalize_csv(file_bytes: bytes) -> list[dict]:
    """
    Parse a Chase CSV export into normalized rows.

    Chase columns: Transaction Date, Post Date, Description, Category, Type,
    Amount, Memo.

    Return a list of dicts with canonical keys:
      raw_description : str   (Chase "Description")
      source_category : str   (Chase "Category")
      amount          : Decimal
      transaction_date: date  (parsed from "Transaction Date", MM/DD/YYYY)
      row_index       : int   (0-based position in the file, for idempotency)

    Note: does NOT assign mcc — resolution happens later via resolve_mcc().
    """
    # TODO: decode bytes -> csv.DictReader; map columns -> canonical keys
    raise NotImplementedError
