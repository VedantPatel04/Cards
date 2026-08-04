"""
Review endpoint tests.

The review loop is the primary categorization engine now, so these cover both
its behaviour and its isolation: one user must never see or affect another
user's merchants.
"""

from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
import services.category_resolver as resolver_module
from apps.transactions.models import MerchantResolution, Transactions


class ReviewTestCase(APITestCase):
    def setUp(self):
        resolver_module._reward_categories = None
        self.queue_url = reverse("review_queue")
        self.answer_url = reverse("review_answer")
        self.user_card = seeds.make_user_card()
        self.user = self.user_card.user
        self.upload = seeds.make_upload(user=self.user)
        self.client.force_authenticate(user=self.user)
        patcher = patch.object(resolver_module, "cache_set")
        patcher.start()
        self.addCleanup(patcher.stop)

    def add_transaction(self, merchant_key, category="", amount="10.00", row_index=0, **kw):
        return seeds.make_transaction(
            upload=self.upload,
            user_card=self.user_card,
            merchant_key=merchant_key,
            category=category,
            amount=Decimal(amount),
            row_index=row_index,
            description=kw.pop("description", merchant_key),
            normalized_description=kw.pop("normalized_description", merchant_key.title()),
            **kw,
        )


class ReviewAuthTests(ReviewTestCase):
    def test_queue_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.queue_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_answer_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(self.answer_url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class ReviewQueueTests(ReviewTestCase):
    def test_lists_only_uncategorized_merchants(self):
        self.add_transaction("MYSTERY VENDOR", category="", row_index=0)
        self.add_transaction("WAL MART", category="groceries", row_index=1)

        resp = self.client.get(self.queue_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        keys = [item["merchant_key"] for item in resp.data["merchants"]]
        self.assertEqual(keys, ["MYSTERY VENDOR"])

    def test_queue_response_has_display_and_raw_fields(self):
        """display_name is the clean name; sample_description is the raw bank string."""
        self.add_transaction(
            "MYSTERY VENDOR",
            description="SQ *MYSTERY VENDOR 0042 NYC",
            normalized_description="Mystery Vendor",
            row_index=0,
        )
        item = self.client.get(self.queue_url).data["merchants"][0]
        self.assertIn("display_name", item)
        self.assertIn("sample_description", item)

    def test_groups_rows_and_totals_spend(self):
        self.add_transaction("MYSTERY VENDOR", amount="10.00", row_index=0)
        self.add_transaction("MYSTERY VENDOR", amount="15.00", row_index=1)

        item = self.client.get(self.queue_url).data["merchants"][0]
        self.assertEqual(item["transaction_count"], 2)
        self.assertEqual(item["total_amount"], "25.00")

    def test_ordered_by_spend_so_biggest_question_is_first(self):
        self.add_transaction("SMALL", amount="5.00", row_index=0)
        self.add_transaction("BIG", amount="500.00", row_index=1)

        keys = [i["merchant_key"] for i in self.client.get(self.queue_url).data["merchants"]]
        self.assertEqual(keys, ["BIG", "SMALL"])

    def test_offers_the_valid_category_vocabulary(self):
        resp = self.client.get(self.queue_url)
        self.assertIn("dining", resp.data["categories"])

    def test_another_users_unknowns_are_invisible(self):
        stranger_card = seeds.make_user_card()
        seeds.make_transaction(
            upload=seeds.make_upload(user=stranger_card.user),
            user_card=stranger_card,
            merchant_key="STRANGER MERCHANT",
            category="",
        )
        resp = self.client.get(self.queue_url)
        self.assertEqual(resp.data["merchants"], [])


class ReviewAnswerTests(ReviewTestCase):
    def test_saves_override_and_backfills_transactions(self):
        self.add_transaction("MYSTERY VENDOR", row_index=0)
        self.add_transaction("MYSTERY VENDOR", row_index=1)

        resp = self.client.post(
            self.answer_url,
            {"merchant_key": "MYSTERY VENDOR", "category": "entertainment"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["transactions_updated"], 2)

        override = MerchantResolution.objects.get(user=self.user, merchant_key="MYSTERY VENDOR")
        self.assertEqual(override.category, "entertainment")
        self.assertEqual(override.source, "user")
        self.assertFalse(
            Transactions.objects.filter(merchant_key="MYSTERY VENDOR", category="").exists()
        )

    def test_answer_warms_the_users_cache_namespace(self):
        self.add_transaction("MYSTERY VENDOR")
        with patch("apps.transactions.views.cache_set") as mock_set:
            self.client.post(
                self.answer_url,
                {"merchant_key": "MYSTERY VENDOR", "category": "dining"},
                format="json",
            )
        mock_set.assert_called_once_with(self.user.pk, "MYSTERY VENDOR", "dining")

    def test_user_answer_overrides_a_bank_supplied_category(self):
        """The user is the authority: Chase calling Amazon 'Shopping' is a default, not a verdict."""
        self.add_transaction("AMAZON", category="shopping", row_index=0)

        resp = self.client.post(
            self.answer_url,
            {"merchant_key": "AMAZON", "category": "groceries"},
            format="json",
        )
        self.assertEqual(resp.data["transactions_updated"], 1)
        self.assertEqual(Transactions.objects.get(merchant_key="AMAZON").category, "groceries")

    def test_reposting_the_same_answer_is_idempotent(self):
        self.add_transaction("MYSTERY VENDOR")
        payload = {"merchant_key": "MYSTERY VENDOR", "category": "dining"}
        self.client.post(self.answer_url, payload, format="json")
        second = self.client.post(self.answer_url, payload, format="json")

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["transactions_updated"], 0)  # nothing left to change
        self.assertEqual(
            MerchantResolution.objects.filter(user=self.user, merchant_key="MYSTERY VENDOR").count(),
            1,
        )

    def test_rejects_category_outside_vocabulary(self):
        self.add_transaction("MYSTERY VENDOR")
        resp = self.client.post(
            self.answer_url,
            {"merchant_key": "MYSTERY VENDOR", "category": "crypto"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MerchantResolution.objects.exists())

    def test_rejects_missing_merchant_key(self):
        resp = self.client.post(self.answer_url, {"category": "dining"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_label_a_merchant_you_do_not_have(self):
        """Blocks filling the table with arbitrary attacker-chosen keys."""
        resp = self.client.post(
            self.answer_url,
            {"merchant_key": "NEVER SEEN", "category": "dining"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(MerchantResolution.objects.exists())

    def test_cannot_relabel_another_users_transactions(self):
        stranger_card = seeds.make_user_card()
        stranger_tx = seeds.make_transaction(
            upload=seeds.make_upload(user=stranger_card.user),
            user_card=stranger_card,
            merchant_key="SHARED MERCHANT",
            category="",
        )
        self.add_transaction("SHARED MERCHANT", row_index=0)

        resp = self.client.post(
            self.answer_url,
            {"merchant_key": "SHARED MERCHANT", "category": "travel"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["transactions_updated"], 1)

        stranger_tx.refresh_from_db()
        self.assertEqual(stranger_tx.category, "")
