"""Tiny test-data factory helpers.

Importable from any test as ``import seeds`` (the ``backend/`` dir is the import
root, same as ``apps.*``). Each helper builds a minimal *valid* instance with
sensible defaults so tests can focus on the behaviour under test. Pass keyword
overrides to change any field.
"""

import itertools
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.cards.models import Card_Products, Reward_Rules
from apps.transactions.models import MerchantResolution, Transactions
from apps.uploads.models import Uploads
from apps.users.models import User_cards

User = get_user_model()

# module-level counters keep auto-generated unique fields collision-free
_counter = itertools.count(1)


def _next():
    return next(_counter)


def make_user(**overrides):
    n = _next()
    defaults = {
        "username": f"user{n}",
        "password": "Sup3rSecret!pw",
    }
    defaults.update(overrides)
    password = defaults.pop("password")
    return User.objects.create_user(password=password, **defaults)


def make_card(**overrides):
    n = _next()
    defaults = {
        "name": f"Card {n}",
        "issuer": f"Issuer {n}",
        "network": "Visa",
        "card_type": "credit",
        "annual_fee": Decimal("95.00"),
        "base_reward_rate": Decimal("1.00"),
        "signup_bonus": Decimal("200.00"),
        "signup_bonus_required_spending": Decimal("1000.00"),
    }
    defaults.update(overrides)
    return Card_Products.objects.create(**defaults)


def make_reward_rule(card=None, **overrides):
    card = card or make_card()
    defaults = {
        "card_product": card,
        "category": "dining",
        "reward_unit": "points",
        "reward_rate": Decimal("3.00"),
    }
    defaults.update(overrides)
    return Reward_Rules.objects.create(**defaults)


def make_user_card(user=None, card=None, **overrides):
    user = user or make_user()
    card = card or make_card()
    defaults = {"user": user, "card": card}
    defaults.update(overrides)
    return User_cards.objects.create(**defaults)


def make_upload(user=None, **overrides):
    user = user or make_user()
    n = _next()
    defaults = {
        "user": user,
        "status": "completed",
        "filename": f"statement-{n}.csv",
        "file_hash": f"hash{n}",
    }
    defaults.update(overrides)
    return Uploads.objects.create(**defaults)


def make_transaction(upload=None, user_card=None, **overrides):
    """
    The upload and the card default to the same owner. Review queries filter on
    user_card__user, so a transaction whose card belongs to a different user
    than its upload would be a fixture that cannot happen in production.
    """
    if user_card is None:
        user_card = make_user_card(user=upload.user if upload else None)
    upload = upload or make_upload(user=user_card.user)
    defaults = {
        "upload": upload,
        "user_card": user_card,
        "category": "dining",
        "merchant_key": "COFFEE",
        "normalized_description": "Coffee",
        "amount": Decimal("12.34"),
        "transaction_date": date(2026, 1, 1),
        "description": "coffee",
        "row_index": 0,
        "entry_type": "spend",
    }
    defaults.update(overrides)
    return Transactions.objects.create(**defaults)


def make_merchant_resolution(user=None, **overrides):
    user = user or make_user()
    defaults = {
        "user": user,
        "merchant_key": f"MERCHANT{_next()}",
        "category": "groceries",
        "source": "user",
    }
    defaults.update(overrides)
    return MerchantResolution.objects.create(**defaults)
