"""
Spend summary tests — truth dataset + empty/isolation + HTTP auth/wire format.

Truth dataset:
  dining:    +100, +200, -30 (refund) → net 270.00
  shopping:  +50                    → net  50.00
  other:     -25 (payment)          → net -25.00
  unresolved:+75                    → excluded from by_category
  total_spend=295.00  count=6  unresolved=1  categorized_pct=83.3
  period 2026-01-01→01-31 (31 days)  annualized dining=3179.03
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from services.spending_aggregator import get_spend_summary

ALL_CATEGORIES = {
    "dining", "groceries", "travel", "gas", "entertainment", "shopping", "other"
}


class SpendSummaryServiceTest(TestCase):
    def setUp(self):
        self.user = seeds.make_user()
        self.user_card = seeds.make_user_card(user=self.user)
        self.upload = seeds.make_upload(user=self.user)

        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="dining", amount=Decimal("100.00"),
            transaction_date=date(2026, 1, 1), row_index=0,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="dining", amount=Decimal("200.00"),
            transaction_date=date(2026, 1, 31), row_index=1,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="dining", amount=Decimal("-30.00"),
            transaction_date=date(2026, 1, 15),
            merchant_key="DINING_REFUND", row_index=2,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="shopping", amount=Decimal("50.00"),
            transaction_date=date(2026, 1, 10), row_index=3,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="other", amount=Decimal("-25.00"),
            transaction_date=date(2026, 1, 5),
            merchant_key="PAYMENT", row_index=4,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="", amount=Decimal("75.00"),
            transaction_date=date(2026, 1, 20),
            merchant_key="UNKNOWN_VENDOR", row_index=5,
        )

    def test_truth_dataset(self):
        """One test covers nets, negatives, unresolved, zeros, period, annualized."""
        s = get_spend_summary(self.user)

        self.assertEqual(set(s["by_category"].keys()), ALL_CATEGORIES)
        self.assertEqual(set(s["annualized"].keys()), ALL_CATEGORIES)
        self.assertNotIn("", s["by_category"])

        self.assertEqual(s["by_category"]["dining"], Decimal("270.00"))
        self.assertEqual(s["by_category"]["shopping"], Decimal("50.00"))
        self.assertEqual(s["by_category"]["other"], Decimal("-25.00"))
        for cat in ("groceries", "travel", "gas", "entertainment"):
            self.assertEqual(s["by_category"][cat], Decimal("0"))

        self.assertEqual(s["total_spend"], Decimal("295.00"))
        self.assertEqual(s["transaction_count"], 6)
        self.assertEqual(s["unresolved_count"], 1)
        self.assertEqual(s["unresolved_amount"], Decimal("75.00"))
        self.assertEqual(s["categorized_pct"], Decimal("83.3"))

        self.assertEqual(s["period"]["earliest"], date(2026, 1, 1))
        self.assertEqual(s["period"]["latest"], date(2026, 1, 31))
        self.assertEqual(s["period"]["days_span"], 31)
        # 270 × 365 / 31 = 3179.032… → 3179.03
        self.assertEqual(s["annualized"]["dining"], Decimal("3179.03"))

    def test_empty_wallet(self):
        s = get_spend_summary(seeds.make_user())
        self.assertEqual(s["transaction_count"], 0)
        self.assertEqual(s["total_spend"], Decimal("0"))
        self.assertEqual(s["unresolved_count"], 0)
        self.assertEqual(s["unresolved_amount"], Decimal("0"))
        self.assertIsNone(s["period"]["earliest"])
        self.assertEqual(s["period"]["days_span"], 0)
        self.assertEqual(s["categorized_pct"], Decimal("100.0"))
        self.assertEqual(set(s["by_category"].keys()), ALL_CATEGORIES)
        self.assertTrue(all(v == Decimal("0") for v in s["by_category"].values()))
        self.assertTrue(all(v == Decimal("0") for v in s["annualized"].values()))

    def test_user_isolation(self):
        other = seeds.make_user_card()
        seeds.make_transaction(
            upload=seeds.make_upload(user=other.user),
            user_card=other,
            category="dining",
            amount=Decimal("999.00"),
            row_index=0,
        )
        s = get_spend_summary(self.user)
        self.assertEqual(s["by_category"]["dining"], Decimal("270.00"))
        self.assertEqual(s["transaction_count"], 6)


class SpendSummaryAPITest(APITestCase):
    def setUp(self):
        self.url = reverse("spend_summary")
        self.user_card = seeds.make_user_card()
        self.user = self.user_card.user
        self.upload = seeds.make_upload(user=self.user)
        self.client.force_authenticate(user=self.user)
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="dining", amount=Decimal("100.00"), row_index=0,
        )

    def test_auth_required(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wire_format_and_scoping(self):
        """Money as 2-decimal strings; stranger's txs never leak into response."""
        other = seeds.make_user_card()
        seeds.make_transaction(
            upload=seeds.make_upload(user=other.user),
            user_card=other,
            category="dining",
            amount=Decimal("999.00"),
            row_index=0,
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        for key in (
            "period", "by_category", "annualized", "total_spend",
            "transaction_count", "unresolved_count", "unresolved_amount",
            "categorized_pct",
        ):
            self.assertIn(key, resp.data)

        self.assertEqual(set(resp.data["by_category"].keys()), ALL_CATEGORIES)
        self.assertEqual(resp.data["by_category"]["dining"], "100.00")
        self.assertEqual(resp.data["by_category"]["groceries"], "0.00")
        self.assertEqual(resp.data["total_spend"], "100.00")
        self.assertEqual(resp.data["transaction_count"], 1)
        self.assertEqual(resp.data["categorized_pct"], "100.0")
        self.assertEqual(resp.data["period"]["days_span"], 1)
