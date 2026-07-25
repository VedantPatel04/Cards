from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from apps.transactions.models import MCC_Codes, Transactions
from services.merchant_normalize import merchant_key

import seeds


class TransactionsConstraintTests(TestCase):
    def test_unique_upload_row_index_pair(self):
        upload = seeds.make_upload()
        user_card = seeds.make_user_card()
        mcc = seeds.make_mcc()
        seeds.make_transaction(upload=upload, user_card=user_card, mcc_code=mcc, row_index=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                seeds.make_transaction(
                    upload=upload, user_card=user_card, mcc_code=mcc, row_index=0
                )

    def test_same_row_index_different_upload_allowed(self):
        user_card = seeds.make_user_card()
        mcc = seeds.make_mcc()
        seeds.make_transaction(
            upload=seeds.make_upload(), user_card=user_card, mcc_code=mcc, row_index=0
        )
        seeds.make_transaction(
            upload=seeds.make_upload(), user_card=user_card, mcc_code=mcc, row_index=0
        )
        self.assertEqual(Transactions.objects.filter(row_index=0).count(), 2)


class MCCCodesTests(TestCase):
    def test_code_is_primary_key(self):
        mcc = seeds.make_mcc(code="5812", category="dining")
        self.assertEqual(mcc.pk, "5812")

    def test_duplicate_code_rejected(self):
        seeds.make_mcc(code="5411", category="groceries")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MCC_Codes.objects.create(code="5411", category="dining")

    def test_protect_blocks_delete_of_referenced_mcc(self):
        mcc = seeds.make_mcc()
        seeds.make_transaction(mcc_code=mcc)
        # on_delete=PROTECT should prevent removing an MCC a transaction references
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                mcc.delete()


class MerchantKeyTests(SimpleTestCase):
    """Pure unit tests — no DB. merchant_key must stay deterministic forever."""

    def test_chase_sample_rows(self):
        cases = [
            ("WAL-MART #2297", "WAL MART"),
            ("PERUSALL E-BOOK", "PERUSALL E BOOK"),
            ("MCDONALD'S F31398", "MCDONALDS"),
            ("MCDONALD'S F25696", "MCDONALDS"),
            ("PMUSA 304046 JERSEY CI", "PMUSA JERSEY CI"),
            ("MTA*NYCT PAYGO", "MTA"),
            ("LYFT   *AIRPORT 07-06", "LYFT"),
            ("LYFT   *WAITSAVE 07-06", "LYFT"),
            ("FOREIGN TRANSACTION FEE", "FOREIGN TRANSACTION FEE"),
            ("DOMINOS PIZZA #10278", "DOMINOS PIZZA"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(merchant_key(raw), expected)

    def test_store_variants_collapse(self):
        """Same merchant, different store numbers → identical key (cache hit)."""
        self.assertEqual(
            merchant_key("MCDONALD'S F31398"),
            merchant_key("MCDONALD'S F25696"),
        )
        self.assertEqual(
            merchant_key("WAL-MART #2297"),
            merchant_key("WAL-MART #0001"),
        )

    def test_star_and_hash_cut_processor_noise(self):
        self.assertEqual(merchant_key("MTA*NYCT PAYGO"), "MTA")
        self.assertEqual(merchant_key("LYFT*RIDE HELP.LYFT.COM"), "LYFT")
        self.assertEqual(merchant_key("SQ *COFFEE SHOP"), "SQ")
        self.assertEqual(merchant_key("AMZN*MARKETPLACE"), "AMZN")

    def test_lowercase_and_whitespace_normalized(self):
        self.assertEqual(merchant_key("  mcdonald's   f99  "), "MCDONALDS")
        self.assertEqual(merchant_key("wal-mart"), "WAL MART")

    def test_empty_and_garbage_inputs(self):
        """Never raise — empty key is a valid miss for later tiers."""
        self.assertEqual(merchant_key(""), "")
        self.assertEqual(merchant_key("   "), "")
        self.assertEqual(merchant_key("***"), "")
        self.assertEqual(merchant_key("###"), "")
        self.assertEqual(merchant_key("12345"), "")
        self.assertEqual(merchant_key(None), "")
        self.assertEqual(merchant_key(123), "")  # type: ignore[arg-type]
