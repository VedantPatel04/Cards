from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import CustomUser, User_cards

import seeds


class RegisterEndpointTests(APITestCase):
    def setUp(self):
        self.url = reverse("register")
        self.payload = {
            "username": "alice",
            "email": "alice@example.com",
            "password": "Sup3rSecret!pw",
            "password2": "Sup3rSecret!pw",
        }

    def test_creates_regular_user(self):
        resp = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        user = CustomUser.objects.get(username="alice")
        self.assertEqual(user.email, "alice@example.com")
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_password_is_hashed_not_stored_plaintext(self):
        self.client.post(self.url, self.payload, format="json")
        user = CustomUser.objects.get(username="alice")
        self.assertNotEqual(user.password, self.payload["password"])
        self.assertTrue(user.check_password(self.payload["password"]))

    def test_response_does_not_leak_password(self):
        resp = self.client.post(self.url, self.payload, format="json")
        self.assertNotIn("password", resp.data)
        self.assertNotIn("password2", resp.data)

    def test_rejects_password_mismatch(self):
        payload = {**self.payload, "password2": "different!pw"}
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomUser.objects.filter(username="alice").exists())

    def test_rejects_duplicate_username(self):
        self.client.post(self.url, self.payload, format="json")
        dup = {**self.payload, "email": "other@example.com"}
        resp = self.client.post(self.url, dup, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CustomUser.objects.filter(username="alice").count(), 1)

    def test_rejects_duplicate_email(self):
        self.client.post(self.url, self.payload, format="json")
        dup = {**self.payload, "username": "bob"}
        resp = self.client.post(self.url, dup, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomUser.objects.filter(username="bob").exists())

    def test_register_is_public(self):
        resp = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class HealthCheckTests(APITestCase):
    def test_returns_ok_unauthenticated(self):
        resp = self.client.get(reverse("health_check"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "ok")
        self.assertIn("db", resp.data)


class UserCardsConstraintTests(TestCase):
    def test_unique_user_card_pair(self):
        user = seeds.make_user()
        card = seeds.make_card()
        User_cards.objects.create(user=user, card=card)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User_cards.objects.create(user=user, card=card)

    def test_same_card_different_users_allowed(self):
        card = seeds.make_card()
        seeds.make_user_card(user=seeds.make_user(), card=card)
        seeds.make_user_card(user=seeds.make_user(), card=card)
        self.assertEqual(User_cards.objects.filter(card=card).count(), 2)
