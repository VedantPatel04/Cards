"""
CSV adapter.

The ONLY place that knows a specific bank's column names. Its job is to turn
raw file bytes into a list of normalized row dicts that the pipeline and
resolver understand. Add one function per source (Chase now, Plaid later) and
nothing downstream changes.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal


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

    Sign convention: Chase marks spend as negative; our Transactions model
    uses positive = spend / negative = refund. We negate Chase amounts here
    so the rest of the pipeline never sees bank-specific sign rules.
    """
    csv_string = file_bytes.decode("utf-8")  # raw string of decoded csv bytes
    string_file = io.StringIO(csv_string)  #transforms csv_string into a file-like object that can be fed into DictReader properly
    reader = csv.DictReader(string_file)
    structured_data = []

    for row_index, row in enumerate(reader):
        chase_amount = Decimal(row["Amount"])
        structured_data.append({
            "raw_description": row["Description"],
            "source_category": row["Category"],
            "amount": -chase_amount, #negates chase amount so it's positive in the model
            "transaction_date": datetime.strptime(
                row["Transaction Date"], "%m/%d/%Y"
            ).date(),
            "row_index": row_index,
        })
    return structured_data
