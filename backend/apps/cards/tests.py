from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.cards.models import Card_Products, Reward_Rules

import seeds


class CardProductsConstraintTests(TestCase):
    def test_unique_name_issuer_pair(self):
        seeds.make_card(name="Sapphire", issuer="Chase")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                seeds.make_card(name="Sapphire", issuer="Chase")

    def test_same_name_different_issuer_allowed(self):
        seeds.make_card(name="Platinum", issuer="Amex")
        seeds.make_card(name="Platinum", issuer="Citi")
        self.assertEqual(Card_Products.objects.filter(name="Platinum").count(), 2)


class RewardRulesConstraintTests(TestCase):
    def test_unique_card_category_pair(self):
        card = seeds.make_card()
        seeds.make_reward_rule(card=card, category="dining")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                seeds.make_reward_rule(card=card, category="dining")

    def test_same_category_different_card_allowed(self):
        seeds.make_reward_rule(card=seeds.make_card(), category="dining")
        seeds.make_reward_rule(card=seeds.make_card(), category="dining")
        self.assertEqual(Reward_Rules.objects.filter(category="dining").count(), 2)


class CardProductsTimestampTests(TestCase):
    def test_updated_at_changes_on_save(self):
        card = seeds.make_card()
        original = card.updated_at
        card.network = "Mastercard"
        card.save()
        card.refresh_from_db()
        self.assertGreater(card.updated_at, original)
