"""
Recommendations API test.

auth, wire shape, empty-wallet len ≤ 3."""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from services.card_catalog_ingestion import ingest_card_catalog


class RecommendationsAPITest(APITestCase):
    def setUp(self):
        ingest_card_catalog()
        self.url = reverse("recommendations")
        self.user = seeds.make_user()
        self.client.force_authenticate(user=self.user)

    def test_auth_required(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wire_shape_empty_wallet(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("confidence", resp.data)
        self.assertIn("confidence_note", resp.data)
        self.assertIn("recommendations", resp.data)
        self.assertLessEqual(len(resp.data["recommendations"]), 3)
        # sparse txs means low confidence
        self.assertEqual(resp.data["confidence"], "low")

        if not resp.data["recommendations"]:
            return

        rec = resp.data["recommendations"][0]
        for key in (
            "rank", "rank_note", "card_id", "card_name", "issuer", "annual_fee",
            "spending_score", "signup_bonus_score", "signup_bonus_status",
            "signup_bonus_note", "total_score", "explanation",
        ):
            self.assertIn(key, rec)
        self.assertEqual(rec["annual_fee"], str(Decimal(rec["annual_fee"]).quantize(Decimal("0.01"))))
        self.assertIsInstance(rec["annual_fee"], str)
        self.assertIsInstance(rec["total_score"], str)
        self.assertIsInstance(rec["explanation"], list)

    def test_user_scoping(self):
        """User B's spend must not change User A's recommendation payload."""
        from apps.cards.models import Card_Products

        baseline = self.client.get(self.url).data

        shared = Card_Products.objects.get(name="Freedom Unlimited", issuer="Chase")
        other = seeds.make_user_card(card=shared)
        seeds.make_transaction(
            upload=seeds.make_upload(user=other.user),
            user_card=other,
            category="dining",
            amount=Decimal("9999.00"),
            row_index=0,
        )

        after = self.client.get(self.url).data
        self.assertEqual(baseline["confidence"], after["confidence"])
        self.assertEqual(
            [r["card_id"] for r in baseline["recommendations"]],
            [r["card_id"] for r in after["recommendations"]],
        )
        self.assertEqual(
            [r["total_score"] for r in baseline["recommendations"]],
            [r["total_score"] for r in after["recommendations"]],
        )
