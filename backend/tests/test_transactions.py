from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.transactions.models import MerchantResolution, Transactions

import seeds


class TransactionsConstraintTests(TestCase):
    def test_unique_upload_row_index_pair(self):
        upload = seeds.make_upload()
        user_card = seeds.make_user_card()
        seeds.make_transaction(upload=upload, user_card=user_card, row_index=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                seeds.make_transaction(
                    upload=upload, user_card=user_card, row_index=0
                )

    def test_same_row_index_different_upload_allowed(self):
        user_card = seeds.make_user_card()
        seeds.make_transaction(
            upload=seeds.make_upload(), user_card=user_card, row_index=0
        )
        seeds.make_transaction(
            upload=seeds.make_upload(), user_card=user_card, row_index=0
        )
        self.assertEqual(Transactions.objects.filter(row_index=0).count(), 2)


class MerchantResolutionConstraintTests(TestCase):
    def test_one_answer_per_user_per_merchant(self):
        user = seeds.make_user()
        seeds.make_merchant_resolution(user=user, merchant_key="TRADER JOES")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                seeds.make_merchant_resolution(user=user, merchant_key="TRADER JOES")

    def test_two_users_may_label_the_same_merchant_differently(self):
        seeds.make_merchant_resolution(
            user=seeds.make_user(), merchant_key="AMAZON", category="groceries"
        )
        seeds.make_merchant_resolution(
            user=seeds.make_user(), merchant_key="AMAZON", category="shopping"
        )
        self.assertEqual(
            MerchantResolution.objects.filter(merchant_key="AMAZON").count(), 2
        )
