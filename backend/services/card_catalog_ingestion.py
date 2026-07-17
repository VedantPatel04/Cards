import json, os
from apps.cards.models import Card_Products, Reward_Rules
from django.conf import settings
from django.db import transaction

CATALOG_PATH = os.path.join(settings.BASE_DIR, 'data', 'card_catalog', 'card_catalog.json')


def load_card_catalog():
    # single place that knows the file location + shape; ingestion AND tests both call this,
    with open(CATALOG_PATH, 'r') as file:
        return json.load(file)


@transaction.atomic
def ingest_card_catalog():
    card_data = load_card_catalog()
    for card_product in card_data: # loop thru each card_product dictionary
        card_obj, created = Card_Products.objects.update_or_create( #upsert card_product in
            name = card_product["name"], #natural key - used to identify duplicates
            issuer = card_product["issuer"], #natural key - used to identify duplicates

            defaults = {
                "network" : card_product["network"],
                "card_type" : card_product["card_type"],
                "annual_fee" : card_product["annual_fee"],
                "base_reward_rate" : card_product["base_reward_rate"],
                "signup_bonus" : card_product["signup_bonus"],
                "signup_bonus_required_spending" : card_product["signup_bonus_required_spending"]
                }
        )
        for rule in card_product["reward_rules"]: #runs for Reward Rules for each card_product
            reward_rule_obj, created = Reward_Rules.objects.update_or_create(
                card_product = card_obj,
                category = rule["category"],
                defaults = {
                    "reward_unit" :rule["reward_unit"],
                    "reward_rate" : rule["reward_rate"],
                }
            )
