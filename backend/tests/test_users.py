from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import CustomUser, User_cards

import seeds


class RegisterEndpointTests(APITestCase):
    def setUp(self):
        self.url = reverse("register") # resolves the "register" url name to /api/register/
        self.payload = { # valid registration data reused across tests; individual tests override specific fields
            "username": "alice",
            "email": "alice@example.com",
            "password": "Sup3rSecret!pw",
            "password2": "Sup3rSecret!pw",
        }

    def test_creates_regular_user(self):
        resp = self.client.post(self.url, self.payload, format="json") # self.client is a fake HTTP client (like Postman) — no server needed
                                                                    # post() sends a POST request to the given URL with the pre-set payload in setUp()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        user = CustomUser.objects.get(username="alice") # fetch the user that was just created from the DB
        self.assertEqual(user.email, "alice@example.com")
        # must be a regular account, not a superuser/admin
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        
    def test_password_is_hashed_not_stored_plaintext(self):
        self.client.post(self.url, self.payload, format="json")
        user = CustomUser.objects.get(username="alice") # fetch alice from the DB to inspect the stored password field directly
        self.assertNotEqual(user.password, self.payload["password"])
        self.assertTrue(user.check_password(self.payload["password"]))

    def test_response_does_not_leak_password(self):
        resp = self.client.post(self.url, self.payload, format="json")
        self.assertNotIn("password", resp.data)
        self.assertNotIn("password2", resp.data)

    def test_rejects_password_mismatch(self):
        payload = {**self.payload, "password2": "different!pw"} # copy self.payload but override password2 so the two passwords don't match
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomUser.objects.filter(username="alice").exists())

    def test_rejects_duplicate_username(self):
        self.client.post(self.url, self.payload, format="json") # register alice first so the username already exists in the DB
        dup = {**self.payload, "email": "other@example.com"} # same username as alice, different email — this is the duplicate attempt
        resp = self.client.post(self.url, dup, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CustomUser.objects.filter(username="alice").count(), 1)

    def test_rejects_duplicate_email(self):
        self.client.post(self.url, self.payload, format="json") # register alice first so the email already exists in the DB
        dup = {**self.payload, "username": "bob"} # different username but same email as alice — this is the duplicate attempt
        resp = self.client.post(self.url, dup, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomUser.objects.filter(username="bob").exists())

    def test_register_is_public(self):
        # no auth header sent; default DRF permission is IsAuthenticated
        resp = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class UserCardsConstraintTests(TestCase):
    def test_unique_user_card_pair(self):
        user = seeds.make_user()
        card = seeds.make_card()
        User_cards.objects.create(user=user, card=card) # first insert always succeeds
        with self.assertRaises(IntegrityError): # assertRaises flips the logic: the test PASSES only if this error IS raised
            with transaction.atomic(): # required when deliberately triggering a DB error — rolls back only this inner block so the rest of the test stays usable
                User_cards.objects.create(user=user, card=card) # identical (user, card) pair — DB should reject this

    def test_same_card_different_users_allowed(self):
        card = seeds.make_card()
        seeds.make_user_card(user=seeds.make_user(), card=card) # user 1 gets the card
        # different user, same card should be fine
        seeds.make_user_card(user=seeds.make_user(), card=card) # user 2 gets the same card — constraint is on the PAIR, not the card alone
        self.assertEqual(User_cards.objects.filter(card=card).count(), 2)
