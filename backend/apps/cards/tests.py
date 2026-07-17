from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from services.card_catalog_ingestion import ingest_card_catalog, load_card_catalog
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

    def test_loads_expected_card_data(self): 
        ingest_card_catalog()
        catalog = load_card_catalog() # sync with the catalog snapshot

        for entry in catalog:
            card = Card_Products.objects.get(name=entry["name"], issuer=entry["issuer"])
            self.assertEqual(card.network, entry["network"])
            self.assertEqual(card.card_type, entry["card_type"])
            self.assertEqual(card.annual_fee, Decimal(entry["annual_fee"]))
            self.assertEqual(card.base_reward_rate, Decimal(entry["base_reward_rate"]))
            self.assertEqual(card.signup_bonus, Decimal(entry["signup_bonus"]))
            self.assertEqual(
                card.signup_bonus_required_spending,
                Decimal(entry["signup_bonus_required_spending"]),
            )

            for rule_entry in entry["reward_rules"]:
                rule = Reward_Rules.objects.get(card_product=card, category=rule_entry["category"])
                self.assertEqual(rule.reward_unit, rule_entry["reward_unit"])
                self.assertEqual(rule.reward_rate, Decimal(rule_entry["reward_rate"]))

    def test_rerun_updates_changed_field_in_place_without_duplicating(self):
        ingest_card_catalog()
        catalog = load_card_catalog()
        entry = catalog[0] # pick whichever card happens to be first in the snapshot -- no name hardcoded
        card = Card_Products.objects.get(name=entry["name"], issuer=entry["issuer"])

        # simulate stale/incorrect data sitting in the DB before a re-ingest
        card.network = "WRONG_NETWORK" # NOTE:only changes Python obj, not DB entry
        card.save() # NOTE NOW Django runs UPDATE → DB is changed


        ingest_card_catalog() # re-running should overwritese stale value back to original snapshot value
        card.refresh_from_db()
        self.assertEqual(card.network, entry["network"])
        # UPDATE the existing row, not insert a second row for the same (name, issuer)
        self.assertEqual(
            Card_Products.objects.filter(name=entry["name"], issuer=entry["issuer"]).count(), 1
        )

    def test_rerun_does_not_duplicate_reward_rules_when_rate_changes(self):
        ingest_card_catalog()
        catalog = load_card_catalog()
        entry = next(e for e in catalog if e["reward_rules"]) # first card that actually has rules
        rule_entry = entry["reward_rules"][0]

        card = Card_Products.objects.get(name=entry["name"], issuer=entry["issuer"])
        rule = Reward_Rules.objects.get(card_product=card, category=rule_entry["category"])
        # simulates a stale rate sitting in the DB
        rule.reward_rate = Decimal("1.00")
        rule.save()

        ingest_card_catalog()
        rule.refresh_from_db()
        self.assertEqual(rule.reward_rate, Decimal(rule_entry["reward_rate"]))
        self.assertEqual(
            Reward_Rules.objects.filter(card_product=card, category=rule_entry["category"]).count(), 1
        )