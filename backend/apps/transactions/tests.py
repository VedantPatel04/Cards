from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.transactions.models import MCC_Codes, Transactions

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
