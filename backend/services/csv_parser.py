"""
CSV adapter.

The ONLY place that knows a specific bank's column names. Its job is to turn
raw file bytes into a list of normalized row dicts that the pipeline and
resolver understand. Add one function per source (Chase now, Plaid later) and
nothing downstream changes.
"""

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

CHASE_DATE_FORMAT = "%m/%d/%Y"

# A file missing any of these is not a Chase export — reject it before parsing
# rather than dying on a KeyError halfway through.
REQUIRED_CHASE_COLUMNS = ("Transaction Date", "Description", "Category", "Amount")

# Optional column: our own tester CSVs may carry a known MCC per row, which
# lets resolve_mcc() short-circuit at Tier 1. Chase exports never have it.
OPTIONAL_MCC_COLUMN = "MCC"

# Chase's "Category" vocabulary -> our canonical category names (the keys of
# mcc_resolver.REPRESENTATIVE_MCC). Provider vocabulary is format knowledge, so
# it belongs here next to the column names: the Plaid adapter will ship its own
# map and emit the same canonical values, and the resolver stays provider-blind.
# A category we deliberately do not map falls through to Tier 6 (uncategorized),
# which is more honest than guessing a bucket.
CHASE_CATEGORY_MAP = {
    "Groceries": "groceries",
    "Food & Drink": "dining",
    "Travel": "travel",
    "Shopping": "shopping",
    "Gas": "gas",
    "Entertainment": "entertainment",
    "Fees & Adjustments": "other",
}

# Transactions.description is varchar(255) and Transactions.amount is
# Decimal(10, 2). Enforcing both here turns a malformed file into a 400 from
# the view instead of a DataError 500 from Postgres.
MAX_DESCRIPTION_CHARS = 255
MAX_ABS_AMOUNT = Decimal("99999999.99")


def _clean_cells(raw_row: dict) -> dict:
    """
    Strip whitespace from every header/value and drop csv's overflow key.

    DictReader stores values with no matching header under the key None, and
    fills missing values with None; normalizing both here keeps the parse loop
    free of null checks.
    """
    return {
        key.strip(): (value or "").strip()
        for key, value in raw_row.items()
        if key is not None
    }


def _parse_amount(raw: str) -> Decimal:
    """Chase writes plain '-35.34', but tolerate '$1,234.56' style exports too."""
    return Decimal(raw.replace("$", "").replace(",", ""))


def normalize_csv(file_bytes: bytes) -> list[dict]:
    """
    Parse a Chase CSV export into normalized rows.

    Chase columns: Transaction Date, Post Date, Description, Category, Type,
    Amount, Memo.

    Return a list of dicts with canonical keys:
      raw_description : str   (Chase "Description")
      source_category : str   (Chase "Category", verbatim — kept for debugging)
      category        : str   (canonical bucket, "" when Chase's text is unmapped)
      amount          : Decimal
      transaction_date: date  (parsed from "Transaction Date", MM/DD/YYYY)
      row_index       : int   (0-based position in the file, for idempotency)
      mcc             : str   (only when the file carries an "MCC" column)

    Note: does NOT assign mcc for bank files — resolution happens later via
    resolve_mcc().

    Sign convention: Chase marks spend as negative; our Transactions model
    uses positive = spend / negative = refund. We negate Chase amounts here
    so the rest of the pipeline never sees bank-specific sign rules.

    Raises ValueError on a file that is not parseable as a Chase export (bad
    header, unreadable amount or date) so the caller can answer 400 instead of
    silently storing garbage.
    """
    csv_string = file_bytes.decode("utf-8-sig", errors="replace")  # -sig drops Excel's BOM
    string_file = io.StringIO(csv_string)  # DictReader needs a file-like object
    reader = csv.DictReader(string_file)

    if reader.fieldnames is None:
        raise ValueError("CSV is empty: no header row found")

    header = {(name or "").strip() for name in reader.fieldnames}
    missing = [column for column in REQUIRED_CHASE_COLUMNS if column not in header]
    if missing:
        raise ValueError(f"CSV is missing required Chase column(s): {', '.join(missing)}")

    structured_data = []

    # DictReader already skips fully blank lines, so row_index counts only real
    # records — and it counts them the same way every time the same bytes are
    # parsed, which is what (upload, row_index) idempotency relies on.
    for row_index, raw_row in enumerate(reader):
        row = _clean_cells(raw_row)

        # Trailing ",,,,," filler lines: no description AND no amount is not a
        # transaction. Skipping without renumbering keeps row_index stable.
        if not row.get("Description") and not row.get("Amount"):
            logger.debug("normalize_csv: skipping empty row at index %s", row_index)
            continue

        try:
            chase_amount = _parse_amount(row["Amount"])
        except (InvalidOperation, AttributeError) as exc:
            raise ValueError(
                f"row {row_index}: unreadable Amount {row.get('Amount')!r}"
            ) from exc

        if abs(chase_amount) > MAX_ABS_AMOUNT:
            raise ValueError(
                f"row {row_index}: Amount {row['Amount']!r} exceeds the "
                f"{MAX_ABS_AMOUNT} limit we can store"
            )

        try:
            transaction_date = datetime.strptime(
                row["Transaction Date"], CHASE_DATE_FORMAT
            ).date()
        except ValueError as exc:
            raise ValueError(
                f"row {row_index}: Transaction Date {row.get('Transaction Date')!r} "
                f"is not {CHASE_DATE_FORMAT}"
            ) from exc

        description = row["Description"]
        if len(description) > MAX_DESCRIPTION_CHARS:
            logger.debug("normalize_csv: truncating long description at row %s", row_index)
            description = description[:MAX_DESCRIPTION_CHARS]

        normalized = {
            "raw_description": description,
            "source_category": row["Category"],
            "category": CHASE_CATEGORY_MAP.get(row["Category"], ""),
            "amount": -chase_amount,  # negates chase amount so spend is positive
            "transaction_date": transaction_date,
            "row_index": row_index,
        }

        mcc = row.get(OPTIONAL_MCC_COLUMN)
        if mcc:
            normalized["mcc"] = mcc

        structured_data.append(normalized)

    logger.debug("normalize_csv: parsed %s rows", len(structured_data))
    return structured_data
