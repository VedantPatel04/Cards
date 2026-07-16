from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from services.card_catalog_ingestion import ingest_card_catalog
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

class CardProductIngestionTests(TestCase):
    def test_ingest_is_idempotent_on_rerun(self): #running ingestion twice must not create duplicates
        ingest_card_catalog()
        cards_after_first_run = Card_Products.objects.count()
        rules_after_first_run = Reward_Rules.objects.count()

        ingest_card_catalog() # duplicate run -- counts must be IDENTICAL after the second run
        self.assertEqual(Card_Products.objects.count(), cards_after_first_run)
        self.assertEqual(Reward_Rules.objects.count(), rules_after_first_run)

    def test_loads_expected_card_data(self): #test if ingestion loads expected data
        ingest_card_catalog()
        # .get() already returns the single matching row, or raises DoesNotExist if missing
        card = Card_Products.objects.get(name="Sapphire Preferred", issuer="Chase")
        self.assertEqual(card.annual_fee, Decimal("95.00"))

        rule = Reward_Rules.objects.get(card_product=card, category="dining")
        self.assertEqual(rule.reward_rate, Decimal("3.00"))
        # NOTE --- what if we want to check non-hardcoded values?
    def test_rerun_updates_changed_field_in_place_without_duplicating(self):
        ingest_card_catalog()
        card = Card_Products.objects.get(name="Sapphire Preferred", issuer="Chase")
        # simulate stale/incorrect data sitting in the DB before a re-ingest
        card.network = "WRONG_NETWORK"
        card.save()

        ingest_card_catalog() # re-running should overwrite the stale value back to the snapshot's value
        card.refresh_from_db()
        self.assertEqual(card.network, "Visa")
        # must UPDATE the existing row, not insert a second "Sapphire Preferred" row
        self.assertEqual(
            Card_Products.objects.filter(name="Sapphire Preferred", issuer="Chase").count(), 1
        )

    def test_rerun_does_not_duplicate_reward_rules_when_rate_changes(self):
        ingest_card_catalog()
        card = Card_Products.objects.get(name="Sapphire Preferred", issuer="Chase")
        rule = Reward_Rules.objects.get(card_product=card, category="dining")
        # simulates a stale rate sitting in the DB 
        rule.reward_rate = Decimal("1.00")
        rule.save()

        ingest_card_catalog()
        rule.refresh_from_db()
        self.assertEqual(rule.reward_rate, Decimal("3.00"))
        self.assertEqual(
            Reward_Rules.objects.filter(card_product=card, category="dining").count(), 1
        )