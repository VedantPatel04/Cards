"""
normalize_csv tests.

No DB and no mocks needed — the adapter is pure: bytes in, list of dicts out.
Covers the Chase happy path, the sign flip, and every way a file can be wrong.
"""

import os
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase

from services.csv_parser import CHASE_CATEGORY_MAP, normalize_csv

HEADER = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo"

SAMPLE_CSV_PATH = os.path.join(
    settings.BASE_DIR, "data", "sample_uploads", "Chase Transaction Statement.csv"
)


def _csv(*lines: str) -> bytes:
    return ("\n".join((HEADER, *lines)) + "\n").encode("utf-8")


# Happy path
class NormalizeCsvHappyPathTests(SimpleTestCase):
    def test_returns_one_dict_per_data_row(self):
        rows = normalize_csv(_csv(
            "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,",
            "07/13/2026,07/14/2026,PERUSALL E-BOOK,Shopping,Sale,-15.00,",
        ))
        self.assertEqual(len(rows), 2)

    def test_canonical_keys_only(self):
        rows = normalize_csv(_csv("07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,"))
        self.assertEqual(
            set(rows[0]),
            {
                "raw_description",
                "source_category",
                "category",
                "amount",
                "transaction_date",
                "row_index",
            },
        )

    def test_field_values(self):
        row = normalize_csv(
            _csv("07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,")
        )[0]
        self.assertEqual(row["raw_description"], "WAL-MART #2297")
        self.assertEqual(row["source_category"], "Groceries")
        self.assertEqual(row["amount"], Decimal("35.34"))
        self.assertEqual(row["transaction_date"], date(2026, 7, 16))
        self.assertEqual(row["row_index"], 0)

    def test_uses_transaction_date_not_post_date(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,X,Groceries,Sale,-1.00,"))[0]
        self.assertEqual(row["transaction_date"], date(2026, 7, 16))

    def test_row_index_is_zero_based_and_contiguous(self):
        rows = normalize_csv(_csv(*[
            f"07/0{n}/2026,07/0{n}/2026,MERCHANT {n},Shopping,Sale,-{n}.00," for n in (1, 2, 3)
        ]))
        self.assertEqual([row["row_index"] for row in rows], [0, 1, 2])

    def test_amount_is_decimal_not_float(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,X,Groceries,Sale,-0.10,"))[0]
        self.assertIsInstance(row["amount"], Decimal)
        self.assertEqual(row["amount"], Decimal("0.10"))  # exact, unlike float

    def test_whitespace_is_trimmed(self):
        row = normalize_csv(_csv("  07/16/2026 ,07/17/2026,  WAL-MART #2297 , Groceries ,Sale, -35.34 ,"))[0]
        self.assertEqual(row["raw_description"], "WAL-MART #2297")
        self.assertEqual(row["source_category"], "Groceries")
        self.assertEqual(row["amount"], Decimal("35.34"))

    def test_extra_unknown_columns_are_ignored(self):
        data = (
            "Transaction Date,Post Date,Description,Category,Type,Amount,Memo,Balance\n"
            "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,,1000.00\n"
        ).encode("utf-8")
        row = normalize_csv(data)[0]
        self.assertEqual(row["amount"], Decimal("35.34"))



# Sign convention
class NormalizeCsvSignTests(SimpleTestCase):
    """Chase: spend negative. Us: spend positive, credits negative."""

    def test_chase_negative_spend_becomes_positive(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,WAL-MART,Groceries,Sale,-35.34,"))[0]
        self.assertEqual(row["amount"], Decimal("35.34"))

    def test_chase_positive_credit_becomes_negative(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,PAYMENT THANK YOU,,Payment,250.00,"))[0]
        self.assertEqual(row["amount"], Decimal("-250.00"))

    def test_zero_amount_stays_zero(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,ADJUSTMENT,,Adjustment,0.00,"))[0]
        self.assertEqual(row["amount"], Decimal("0.00"))

    def test_currency_formatting_is_tolerated(self):
        row = normalize_csv(_csv('07/16/2026,07/17/2026,BIG PURCHASE,Shopping,Sale,"-$1,234.56",'))[0]
        self.assertEqual(row["amount"], Decimal("1234.56"))

# Canonical category (the seam every future adapter plugs into)
class NormalizeCsvCategoryTests(SimpleTestCase):
    """
    The adapter owns provider vocabulary and hands the resolver a canonical
    bucket. Keeping this seam is what lets another bank's adapter reuse the
    resolver and the review loop untouched.
    """

    def test_chase_text_becomes_canonical_bucket(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,X,Food & Drink,Sale,-1.00,"))[0]
        self.assertEqual(row["category"], "dining")
        self.assertEqual(row["source_category"], "Food & Drink")  # raw text preserved

    def test_non_bonus_chase_bucket_is_other_not_a_question(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,X,Automotive,Sale,-1.00,"))[0]
        self.assertEqual(row["category"], "other")

    def test_unknown_chase_text_on_spend_is_blank_for_review(self):
        row = normalize_csv(_csv("07/16/2026,07/17/2026,X,Sponsorships,Sale,-1.00,"))[0]
        self.assertEqual(row["category"], "")

    def test_blank_category_on_a_credit_is_other(self):
        """Card payments have no Chase category and are not spend to categorize."""
        row = normalize_csv(_csv("07/16/2026,07/17/2026,PAYMENT,,Payment,250.00,"))[0]
        self.assertEqual(row["category"], "other")

    def test_every_mapped_bucket_is_a_rewards_category(self):
        from services.category_resolver import reward_categories

        cats = reward_categories()
        for chase_text, canonical in CHASE_CATEGORY_MAP.items():
            with self.subTest(chase_text=chase_text):
                self.assertIn(canonical, cats)

# Rows that are not transactions
class NormalizeCsvSkippedRowTests(SimpleTestCase):
    def test_header_only_file_returns_empty_list(self):
        self.assertEqual(normalize_csv((HEADER + "\n").encode("utf-8")), [])

    def test_blank_lines_are_skipped(self):
        data = (HEADER + "\n\n07/16/2026,07/17/2026,X,Groceries,Sale,-1.00,\n\n").encode("utf-8")
        rows = normalize_csv(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["row_index"], 0)

    def test_comma_filler_row_is_skipped(self):
        rows = normalize_csv(_csv(
            "07/16/2026,07/17/2026,X,Groceries,Sale,-1.00,",
            ",,,,,,",
        ))
        self.assertEqual(len(rows), 1)

    def test_skipping_does_not_renumber_later_rows(self):
        """
        row_index must depend only on the bytes, since (upload, row_index) is the
        idempotency key. A skipped row keeps its slot.
        """
        rows = normalize_csv(_csv(
            "07/16/2026,07/17/2026,FIRST,Groceries,Sale,-1.00,",
            ",,,,,,",
            "07/18/2026,07/19/2026,THIRD,Groceries,Sale,-3.00,",
        ))
        self.assertEqual([row["raw_description"] for row in rows], ["FIRST", "THIRD"])
        self.assertEqual([row["row_index"] for row in rows], [0, 2])

# Encoding
class NormalizeCsvEncodingTests(SimpleTestCase):
    def test_utf8_bom_is_stripped_from_first_header(self):
        """
        Excel writes a BOM. Without utf-8-sig the first header becomes
        '\ufeffTransaction Date' and every row raises KeyError.
        """
        data = b"\xef\xbb\xbf" + _csv("07/16/2026,07/17/2026,X,Groceries,Sale,-1.00,")
        rows = normalize_csv(data)
        self.assertEqual(rows[0]["transaction_date"], date(2026, 7, 16))

    def test_non_utf8_bytes_do_not_crash(self):
        data = _csv("07/16/2026,07/17/2026,CAF\xc9,Groceries,Sale,-1.00,".encode("latin-1").decode("latin-1"))
        rows = normalize_csv(data)
        self.assertEqual(len(rows), 1)

# Rejected files (ValueError → the view answers 400)
class NormalizeCsvRejectionTests(SimpleTestCase):
    def test_empty_bytes_raise(self):
        with self.assertRaises(ValueError):
            normalize_csv(b"")

    def test_missing_required_column_raises_and_names_it(self):
        data = b"Transaction Date,Post Date,Description,Type,Memo\n07/16/2026,07/17/2026,X,Sale,\n"
        with self.assertRaises(ValueError) as ctx:
            normalize_csv(data)
        self.assertIn("Category", str(ctx.exception))
        self.assertIn("Amount", str(ctx.exception))

    def test_wrong_bank_file_raises_valueerror_not_keyerror(self):
        data = b"date,merchant,value\n2026-07-16,WALMART,35.34\n"
        with self.assertRaises(ValueError):
            normalize_csv(data)

    def test_unreadable_amount_raises_with_row_number(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_csv(_csv(
                "07/16/2026,07/17/2026,X,Groceries,Sale,-1.00,",
                "07/17/2026,07/18/2026,Y,Groceries,Sale,N/A,",
            ))
        self.assertIn("row 1", str(ctx.exception))

    def test_wrong_date_format_raises_with_row_number(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_csv(_csv("2026-07-16,07/17/2026,X,Groceries,Sale,-1.00,"))
        self.assertIn("row 0", str(ctx.exception))

    def test_amount_too_large_for_the_column_raises(self):
        """
        Transactions.amount is Decimal(10, 2). Catching this here is a 400;
        letting it through is a DataError 500 mid-write.
        """
        with self.assertRaises(ValueError) as ctx:
            normalize_csv(_csv("07/16/2026,07/17/2026,X,Groceries,Sale,-100000000.00,"))
        self.assertIn("row 0", str(ctx.exception))

    def test_more_than_max_upload_rows_raises(self):
        from services.csv_parser import MAX_UPLOAD_ROWS

        lines = [
            f"07/16/2026,07/17/2026,MERCHANT {i},Shopping,Sale,-1.00,"
            for i in range(MAX_UPLOAD_ROWS + 1)
        ]
        with self.assertRaises(ValueError) as ctx:
            normalize_csv(_csv(*lines))
        self.assertIn(str(MAX_UPLOAD_ROWS), str(ctx.exception))


# Column length guards
class NormalizeCsvLengthTests(SimpleTestCase):
    def test_overlong_description_is_truncated_to_column_width(self):
        long_name = "A" * 400
        row = normalize_csv(_csv(f"07/16/2026,07/17/2026,{long_name},Groceries,Sale,-1.00,"))[0]
        self.assertEqual(len(row["raw_description"]), 255)


# The real sample file
class NormalizeCsvSampleFileTests(SimpleTestCase):
    """Parses the actual Chase export committed under data/sample_uploads/."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(SAMPLE_CSV_PATH, "rb") as file:
            cls.rows = normalize_csv(file.read())

    def test_parses_all_fifteen_transactions(self):
        self.assertEqual(len(self.rows), 15)

    def test_first_and_last_rows(self):
        self.assertEqual(self.rows[0]["raw_description"], "WAL-MART #2297")
        self.assertEqual(self.rows[0]["amount"], Decimal("35.34"))
        self.assertEqual(self.rows[-1]["raw_description"], "DOMINOS PIZZA #10278")
        self.assertEqual(self.rows[-1]["amount"], Decimal("33.30"))

    def test_all_amounts_positive_because_file_is_all_spend(self):
        self.assertTrue(all(row["amount"] > 0 for row in self.rows))

    def test_row_indexes_are_unique_and_ordered(self):
        indexes = [row["row_index"] for row in self.rows]
        self.assertEqual(indexes, sorted(indexes))
        self.assertEqual(len(set(indexes)), len(indexes))

    def test_six_identical_mta_rows_share_one_description(self):
        mta = [row for row in self.rows if row["raw_description"] == "MTA*NYCT PAYGO"]
        self.assertEqual(len(mta), 6)

    def test_parsing_is_deterministic(self):
        with open(SAMPLE_CSV_PATH, "rb") as file:
            again = normalize_csv(file.read())
        self.assertEqual(self.rows, again)
