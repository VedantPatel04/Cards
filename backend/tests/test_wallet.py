"""Wallet + catalog endpoint tests."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from apps.cards.models import Card_Products
from apps.transactions.models import Transactions
from apps.uploads.models import Uploads
from apps.users.models import User_cards


class CatalogListTests(APITestCase):
    def setUp(self):
        self.url = reverse("catalog_list")
        self.user = seeds.make_user()
        self.client.force_authenticate(user=self.user)

    def test_lists_active_catalog_cards(self):
        active = seeds.make_card(name="Sapphire Preferred", issuer="Chase")
        seeds.make_card(name="Ghost Card", issuer="Chase", is_active=False)
        Card_Products.objects.create(
            name="Custom Later",
            issuer="Bank",
            network="Visa",
            card_type="credit",
            is_active=True,
            is_catalog=False,
            annual_fee="0.00",
            base_reward_rate="1.00",
            signup_bonus="0.00",
            signup_bonus_required_spending="0.00",
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {c["id"] for c in resp.data["cards"]}
        self.assertIn(active.pk, ids)
        self.assertEqual(resp.data["count"], len(resp.data["cards"]))
        self.assertTrue(all("name" in c and "issuer" in c for c in resp.data["cards"]))

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class WalletTests(APITestCase):
    def setUp(self):
        self.list_url = reverse("wallet")
        self.user = seeds.make_user()
        self.card = seeds.make_card(name="Freedom Unlimited", issuer="Chase")
        self.client.force_authenticate(user=self.user)

    def test_add_list_and_reject_duplicate(self):
        resp = self.client.post(
            self.list_url, {"card_product_id": self.card.pk}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["card_name"], "Freedom Unlimited")
        self.assertEqual(resp.data["card_product_id"], self.card.pk)
        wallet_id = resp.data["id"]

        listed = self.client.get(self.list_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["cards"][0]["id"], wallet_id)

        dup = self.client.post(
            self.list_url, {"card_product_id": self.card.pk}, format="json"
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", dup.data["detail"])
        self.assertEqual(User_cards.objects.filter(user=self.user).count(), 1)

    def test_add_rejects_missing_and_unknown_product(self):
        missing = self.client.post(self.list_url, {}, format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)

        unknown = self.client.post(
            self.list_url, {"card_product_id": 999999}, format="json"
        )
        self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST)

        inactive = seeds.make_card(name="Old Card", issuer="Chase", is_active=False)
        bad = self.client.post(
            self.list_url, {"card_product_id": inactive.pk}, format="json"
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_custom_card(self):
        resp = self.client.post(
            self.list_url,
            {"name": "Campus Visa", "issuer": "Local CU", "network": "Visa"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertFalse(resp.data["is_catalog"])
        self.assertEqual(resp.data["card_name"], "Campus Visa")

        product = Card_Products.objects.get(pk=resp.data["card_product_id"])
        self.assertFalse(product.is_catalog)
        self.assertEqual(product.base_reward_rate, 0)
        self.assertEqual(product.reward_rules.count(), 0)
        self.assertNotIn(product.pk, {
            c["id"] for c in self.client.get(reverse("catalog_list")).data["cards"]
        })

        dup = self.client.post(
            self.list_url,
            {"name": "Campus Visa", "issuer": "Local CU", "network": "Visa"},
            format="json",
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", dup.data["detail"])

    def test_custom_name_matching_catalog_attaches_catalog_card(self):
        resp = self.client.post(
            self.list_url,
            {
                "name": "Freedom Unlimited",
                "issuer": "Chase",
                "network": "Visa",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["card_product_id"], self.card.pk)
        self.assertTrue(resp.data["is_catalog"])

    def test_custom_requires_all_fields(self):
        resp = self.client.post(
            self.list_url,
            {"name": "Only Name", "issuer": "Bank"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("network", resp.data["detail"])

    def test_delete_hard_cascades_transactions(self):
        entry = seeds.make_user_card(user=self.user, card=self.card)
        upload = seeds.make_upload(user=self.user)
        seeds.make_transaction(upload=upload, user_card=entry, row_index=0)
        self.assertEqual(Transactions.objects.filter(user_card=entry).count(), 1)

        resp = self.client.delete(reverse("wallet_delete", kwargs={"wallet_id": entry.pk}))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User_cards.objects.filter(pk=entry.pk).exists())
        self.assertEqual(Transactions.objects.filter(user_card_id=entry.pk).count(), 0)
        # Empty statement shells are cleaned up with the card.
        self.assertFalse(Uploads.objects.filter(pk=upload.pk).exists())
        # Catalog products are kept even when the wallet row is gone.
        self.assertTrue(Card_Products.objects.filter(pk=self.card.pk).exists())

    def test_delete_keeps_uploads_still_holding_transactions(self):
        doomed = seeds.make_user_card(user=self.user, card=self.card)
        kept = seeds.make_user_card(user=self.user)
        empty_upload = seeds.make_upload(user=self.user)
        live_upload = seeds.make_upload(user=self.user)
        seeds.make_transaction(upload=empty_upload, user_card=doomed, row_index=0)
        seeds.make_transaction(upload=live_upload, user_card=kept, row_index=0)

        resp = self.client.delete(reverse("wallet_delete", kwargs={"wallet_id": doomed.pk}))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Uploads.objects.filter(pk=empty_upload.pk).exists())
        self.assertTrue(Uploads.objects.filter(pk=live_upload.pk).exists())
        self.assertEqual(
            Transactions.objects.filter(upload=live_upload, user_card=kept).count(),
            1,
        )

    def test_delete_custom_removes_orphan_product(self):
        add = self.client.post(
            self.list_url,
            {"name": "Temp Card", "issuer": "Temp Bank", "network": "Mastercard"},
            format="json",
        )
        product_id = add.data["card_product_id"]
        wallet_id = add.data["id"]

        resp = self.client.delete(reverse("wallet_delete", kwargs={"wallet_id": wallet_id}))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Card_Products.objects.filter(pk=product_id).exists())

    def test_delete_foreign_wallet_is_404(self):
        stranger = seeds.make_user_card()
        resp = self.client.delete(
            reverse("wallet_delete", kwargs={"wallet_id": stranger.pk})
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(User_cards.objects.filter(pk=stranger.pk).exists())

    def test_wallet_requires_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)


class TransactionListTests(APITestCase):
    def setUp(self):
        self.url = reverse("transaction_list")
        self.user_card = seeds.make_user_card()
        self.user = self.user_card.user
        self.upload = seeds.make_upload(user=self.user)
        self.client.force_authenticate(user=self.user)

    def test_lists_own_transactions_with_card_name(self):
        seeds.make_transaction(
            upload=self.upload,
            user_card=self.user_card,
            description="MCDONALD'S F1",
            merchant_key="MCDONALDS",
            category="dining",
            row_index=0,
        )
        stranger = seeds.make_user_card()
        seeds.make_transaction(
            upload=seeds.make_upload(user=stranger.user),
            user_card=stranger,
            row_index=0,
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        item = resp.data["transactions"][0]
        self.assertEqual(item["user_card_id"], self.user_card.pk)
        self.assertEqual(item["card_name"], self.user_card.card.name)
        self.assertEqual(item["issuer"], self.user_card.card.issuer)
        self.assertEqual(item["upload_id"], self.upload.pk)
        self.assertEqual(item["filename"], self.upload.filename)
        self.assertEqual(item["merchant_key"], "MCDONALDS")
        self.assertEqual(item["category"], "dining")
        self.assertIn("truncated", resp.data)
        self.assertFalse(resp.data["truncated"])

    def test_count_is_total_when_list_is_truncated(self):
        from apps.transactions.views import MAX_TRANSACTION_ITEMS

        for i in range(MAX_TRANSACTION_ITEMS + 3):
            seeds.make_transaction(
                upload=self.upload,
                user_card=self.user_card,
                row_index=i,
                merchant_key=f"M{i}",
            )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], MAX_TRANSACTION_ITEMS + 3)
        self.assertTrue(resp.data["truncated"])
        self.assertEqual(len(resp.data["transactions"]), MAX_TRANSACTION_ITEMS)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
