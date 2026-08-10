"""
Spend summary tests — truth dataset + empty/isolation + HTTP auth/wire format.

Truth dataset:
  dining:    +100, +200, -30 (refund) → net 270.00
  shopping:  +50                    → net  50.00
  other:     -25 (payment)          → excluded from spend → 0.00
  unresolved:+75                    → excluded from by_category
  total_spend=320.00  count=6  unresolved=1  categorized_pct=83.3
  period 2026-01-01→01-31 (31 days, 1 month covered)  annualized dining=3240.00
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from apps.transactions.models import ENTRY_PAYMENT, ENTRY_REFUND, ENTRY_SPEND
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
            entry_type=ENTRY_SPEND,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="dining", amount=Decimal("200.00"),
            transaction_date=date(2026, 1, 31), row_index=1,
            entry_type=ENTRY_SPEND,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="dining", amount=Decimal("-30.00"),
            transaction_date=date(2026, 1, 15),
            merchant_key="DINING_REFUND", row_index=2,
            entry_type=ENTRY_REFUND,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="shopping", amount=Decimal("50.00"),
            transaction_date=date(2026, 1, 10), row_index=3,
            entry_type=ENTRY_SPEND,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="other", amount=Decimal("-25.00"),
            transaction_date=date(2026, 1, 5),
            merchant_key="PAYMENT", row_index=4,
            description="Payment Thank You - Bill",
            entry_type=ENTRY_PAYMENT,
        )
        seeds.make_transaction(
            upload=self.upload, user_card=self.user_card,
            category="", amount=Decimal("75.00"),
            transaction_date=date(2026, 1, 20),
            merchant_key="UNKNOWN_VENDOR", row_index=5,
            entry_type=ENTRY_SPEND,
        )

    def test_truth_dataset(self):
        """Nets include refunds; bill payments are excluded from spend totals."""
        s = get_spend_summary(self.user)

        self.assertEqual(set(s["by_category"].keys()), ALL_CATEGORIES)
        self.assertEqual(set(s["annualized"].keys()), ALL_CATEGORIES)
        self.assertNotIn("", s["by_category"])

        self.assertEqual(s["by_category"]["dining"], Decimal("270.00"))
        self.assertEqual(s["by_category"]["shopping"], Decimal("50.00"))
        self.assertEqual(s["by_category"]["other"], Decimal("0"))
        for cat in ("groceries", "travel", "gas", "entertainment"):
            self.assertEqual(s["by_category"][cat], Decimal("0"))

        self.assertEqual(s["total_spend"], Decimal("320.00"))
        self.assertEqual(s["transaction_count"], 6)
        self.assertEqual(s["unresolved_count"], 1)
        self.assertEqual(s["unresolved_amount"], Decimal("75.00"))
        self.assertEqual(s["categorized_pct"], Decimal("83.3"))

        self.assertEqual(s["period"]["earliest"], date(2026, 1, 1))
        self.assertEqual(s["period"]["latest"], date(2026, 1, 31))
        self.assertEqual(s["period"]["days_span"], 31)
        self.assertEqual(s["period"]["months_covered"], 1)
        self.assertEqual(len(s["period"]["months_breakdown"]), 1)
        self.assertEqual(s["period"]["months_breakdown"][0]["month"], "2026-01")
        self.assertEqual(s["period"]["months_breakdown"][0]["transaction_count"], 6)
        # 270 × 12 / 1
        self.assertEqual(s["annualized"]["dining"], Decimal("3240.00"))

    def test_payment_only_month_still_counts_toward_period(self):
        """A payment-only upload still contributes 1 statement-month of evidence."""
        user = seeds.make_user()
        card = seeds.make_user_card(user=user)
        upload = seeds.make_upload(user=user)
        seeds.make_transaction(
            upload=upload, user_card=card,
            category="other", amount=Decimal("-100.00"),
            transaction_date=date(2026, 2, 10),
            description="Payment Thank You - Bill",
            entry_type=ENTRY_PAYMENT,
            row_index=0,
        )
        s = get_spend_summary(user)
        self.assertEqual(s["total_spend"], Decimal("0"))
        self.assertEqual(s["by_category"]["other"], Decimal("0"))
        self.assertEqual(s["transaction_count"], 1)
        self.assertEqual(s["period"]["months_covered"], 1)
        self.assertEqual(s["period"]["months_breakdown"][0]["month"], "2026-02")

    def test_mid_cycle_statement_is_one_month_not_two_calendar_months(self):
        """15th→14th cycle spans two calendars but one ~30-day statement."""
        user = seeds.make_user()
        card = seeds.make_user_card(user=user)
        upload = seeds.make_upload(user=user)
        seeds.make_transaction(
            upload=upload, user_card=card,
            category="dining", amount=Decimal("40.00"),
            transaction_date=date(2026, 4, 15), row_index=0,
        )
        seeds.make_transaction(
            upload=upload, user_card=card,
            category="dining", amount=Decimal("60.00"),
            transaction_date=date(2026, 5, 14), row_index=1,
        )
        s = get_spend_summary(user)
        self.assertEqual(s["period"]["months_covered"], 1)
        self.assertEqual(
            [row["month"] for row in s["period"]["months_breakdown"]],
            ["2026-04", "2026-05"],
        )
        # 100 × 12 / 1
        self.assertEqual(s["annualized"]["dining"], Decimal("1200.00"))

    def test_two_statements_with_calendar_spill_count_as_two(self):
        """Jan+Feb files touching Dec/Jan/Feb calendars → months_covered=2."""
        user = seeds.make_user()
        card = seeds.make_user_card(user=user)
        jan = seeds.make_upload(user=user, filename="CHASE_JAN.csv")
        feb = seeds.make_upload(user=user, filename="CHASE_FEB.csv")
        seeds.make_transaction(
            upload=jan, user_card=card,
            category="travel", amount=Decimal("100.00"),
            transaction_date=date(2025, 12, 20), row_index=0,
        )
        seeds.make_transaction(
            upload=jan, user_card=card,
            category="dining", amount=Decimal("50.00"),
            transaction_date=date(2026, 1, 10), row_index=1,
        )
        seeds.make_transaction(
            upload=feb, user_card=card,
            category="shopping", amount=Decimal("80.00"),
            transaction_date=date(2026, 1, 25), row_index=0,
        )
        seeds.make_transaction(
            upload=feb, user_card=card,
            category="shopping", amount=Decimal("20.00"),
            transaction_date=date(2026, 2, 2), row_index=1,
        )
        s = get_spend_summary(user)
        self.assertEqual(s["period"]["months_covered"], 2)
        self.assertEqual(len(s["period"]["months_breakdown"]), 3)
        self.assertEqual(s["total_spend"], Decimal("250.00"))

    def test_empty_wallet(self):
        s = get_spend_summary(seeds.make_user())
        self.assertEqual(s["transaction_count"], 0)
        self.assertEqual(s["total_spend"], Decimal("0"))
        self.assertEqual(s["unresolved_count"], 0)
        self.assertEqual(s["unresolved_amount"], Decimal("0"))
        self.assertIsNone(s["period"]["earliest"])
        self.assertEqual(s["period"]["days_span"], 0)
        self.assertEqual(s["period"]["months_covered"], 0)
        self.assertEqual(s["period"]["months_breakdown"], [])
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
        self.assertIn("months_breakdown", resp.data["period"])
        self.assertIsInstance(resp.data["period"]["months_breakdown"], list)
        self.assertEqual(len(resp.data["period"]["months_breakdown"]), 1)
        mb = resp.data["period"]["months_breakdown"][0]
        self.assertIn("month", mb)
        self.assertIn("transaction_count", mb)
