"""Account delete, profile, and admin privilege lockdown tests."""

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from apps.cards.models import Card_Products
from apps.transactions.models import MerchantResolution, Transactions
from apps.uploads.models import Uploads
from apps.users.admin import LockedDownUserAdmin
from apps.users.models import CustomUser, User_cards


class AccountEndpointTests(APITestCase):
    def setUp(self):
        self.url = reverse("account")
        self.password = "Sup3rSecret!pw"
        self.user = seeds.make_user(password=self.password)
        self.client.force_authenticate(user=self.user)

    def test_get_returns_profile(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], self.user.pk)
        self.assertEqual(resp.data["username"], self.user.username)
        self.assertNotIn("email", resp.data)
        self.assertNotIn("password", resp.data)

    def test_delete_requires_password_and_confirm(self):
        bad_confirm = self.client.delete(
            self.url,
            {"password": self.password, "confirm": "please"},
            format="json",
        )
        self.assertEqual(bad_confirm.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CustomUser.objects.filter(pk=self.user.pk).exists())

        bad_pw = self.client.delete(
            self.url,
            {"password": "wrong-password", "confirm": "DELETE"},
            format="json",
        )
        self.assertEqual(bad_pw.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CustomUser.objects.filter(pk=self.user.pk).exists())

    def test_delete_cascades_owned_data(self):
        card = seeds.make_card()
        entry = seeds.make_user_card(user=self.user, card=card)
        upload = seeds.make_upload(user=self.user)
        seeds.make_transaction(upload=upload, user_card=entry, row_index=0)
        seeds.make_merchant_resolution(user=self.user, merchant_key="STARBUCKS")

        custom = Card_Products.objects.create(
            name="My Visa",
            issuer="Local",
            network="Visa",
            card_type="credit",
            is_active=True,
            is_catalog=False,
            owner=self.user,
            annual_fee="0.00",
            base_reward_rate="0.00",
            signup_bonus="0.00",
            signup_bonus_required_spending="0.00",
        )
        seeds.make_user_card(user=self.user, card=custom)

        user_id = self.user.pk
        resp = self.client.delete(
            self.url,
            {"password": self.password, "confirm": "DELETE"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CustomUser.objects.filter(pk=user_id).exists())
        self.assertFalse(User_cards.objects.filter(user_id=user_id).exists())
        self.assertFalse(Uploads.objects.filter(user_id=user_id).exists())
        self.assertFalse(Transactions.objects.filter(user_card__user_id=user_id).exists())
        self.assertFalse(MerchantResolution.objects.filter(user_id=user_id).exists())
        self.assertFalse(Card_Products.objects.filter(pk=custom.pk).exists())
        # Shared catalog product survives.
        self.assertTrue(Card_Products.objects.filter(pk=card.pk).exists())

    def test_delete_keeps_other_users_data(self):
        stranger = seeds.make_user_card()
        seeds.make_upload(user=stranger.user)
        seeds.make_merchant_resolution(user=stranger.user)

        resp = self.client.delete(
            self.url,
            {"password": self.password, "confirm": "DELETE"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(CustomUser.objects.filter(pk=stranger.user_id).exists())
        self.assertTrue(User_cards.objects.filter(pk=stranger.pk).exists())

    def test_cannot_delete_last_superuser(self):
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])

        resp = self.client.delete(
            self.url,
            {"password": self.password, "confirm": "DELETE"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CustomUser.objects.filter(pk=self.user.pk).exists())

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)


class WalletCustomScopingTests(APITestCase):
    def setUp(self):
        self.url = reverse("wallet")
        self.user = seeds.make_user()
        self.other = seeds.make_user()
        self.client.force_authenticate(user=self.user)

    def test_custom_cards_are_not_shared_across_users(self):
        other_client = self.client_class()
        other_client.force_authenticate(user=self.other)
        created = other_client.post(
            self.url,
            {"name": "Campus Visa", "issuer": "Local CU", "network": "Visa"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        other_product_id = created.data["card_product_id"]

        mine = self.client.post(
            self.url,
            {"name": "Campus Visa", "issuer": "Local CU", "network": "Visa"},
            format="json",
        )
        self.assertEqual(mine.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(mine.data["card_product_id"], other_product_id)

        mine_product = Card_Products.objects.get(pk=mine.data["card_product_id"])
        other_product = Card_Products.objects.get(pk=other_product_id)
        self.assertEqual(mine_product.owner_id, self.user.pk)
        self.assertEqual(other_product.owner_id, self.other.pk)
        self.assertFalse(mine_product.is_catalog)

    def test_cannot_add_foreign_custom_by_product_id(self):
        foreign = Card_Products.objects.create(
            name="Secret Custom",
            issuer="Bank",
            network="Visa",
            card_type="credit",
            is_active=True,
            is_catalog=False,
            owner=self.other,
            annual_fee="0.00",
            base_reward_rate="0.00",
            signup_bonus="0.00",
            signup_bonus_required_spending="0.00",
        )
        resp = self.client.post(
            self.url, {"card_product_id": foreign.pk}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            User_cards.objects.filter(user=self.user, card=foreign).exists()
        )


class AdminLockdownTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = LockedDownUserAdmin(CustomUser, self.site)
        self.superuser = seeds.make_user(username="boss")
        self.superuser.is_superuser = True
        self.superuser.is_staff = True
        self.superuser.save()
        self.staff = seeds.make_user(username="clerk")
        self.staff.is_staff = True
        self.staff.save()

    def test_is_superuser_always_readonly(self):
        request = self.factory.get("/admin/")
        request.user = self.superuser
        readonly = self.admin.get_readonly_fields(request, obj=self.staff)
        self.assertIn("is_superuser", readonly)

    def test_save_model_cannot_elevate_to_superuser(self):
        request = self.factory.post("/admin/")
        request.user = self.superuser
        self.staff.is_superuser = True
        self.admin.save_model(request, self.staff, form=None, change=True)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)

    def test_cannot_delete_last_superuser(self):
        request = self.factory.post("/admin/")
        request.user = self.superuser
        self.assertFalse(
            self.admin.has_delete_permission(request, obj=self.superuser)
        )
