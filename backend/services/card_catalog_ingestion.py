import json
import os
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

from apps.cards.models import Card_Products, Reward_Rules
from services.category_resolver import reward_rule_aliases

CATALOG_PATH = os.path.join(settings.BASE_DIR, 'data', 'card_catalog', 'card_catalog.json')

REQUIRED_CARD_KEYS = {
    "name", "issuer", "network", "card_type",
    "annual_fee", "base_reward_rate", "signup_bonus",
    "signup_bonus_required_spending", "reward_rules",
    "signup_bonus_spend_period_months", "signup_bonus_unit",
}
REQUIRED_RULE_KEYS = {"category", "reward_unit", "reward_rate"}
# Always present. The two signup_bonus_* thresholds are handled separately
# because a card with no welcome bonus has nothing to threshold.
DECIMAL_CARD_FIELDS = ("annual_fee", "base_reward_rate", "signup_bonus")
REWARD_CURRENCIES = {"cash_back", "points", "miles"}


def load_card_catalog(): #loads snapshot of card catalog
    with open(CATALOG_PATH, 'r') as file:
        return json.load(file)


def _validate_catalog(card_data): # runs before any DB write — fail loudly with a clear message rather than a raw KeyError
    if not isinstance(card_data, list):
        raise ValueError("card_catalog.json must be a JSON array at the top level")
    if len(card_data) == 0:
        raise ValueError("card_catalog.json is empty — refusing to ingest (would deactivate all cards)")

    for i, entry in enumerate(card_data):
        label = entry.get("name", f"index {i}")

        missing_card_keys = REQUIRED_CARD_KEYS - entry.keys()
        if missing_card_keys: #MISSING CARD DATA
            raise ValueError(f"Card '{label}' is missing required fields: {missing_card_keys}")

        for field in DECIMAL_CARD_FIELDS:
            try:
                Decimal(entry[field])
            except (InvalidOperation, TypeError):
                raise ValueError(
                    f"Card '{label}': '{field}' is not a valid decimal: {entry[field]!r}"
                )

        if entry["signup_bonus_unit"] not in REWARD_CURRENCIES:
            raise ValueError(
                f"Card '{label}': 'signup_bonus_unit' must be one of "
                f"{sorted(REWARD_CURRENCIES)}, got {entry['signup_bonus_unit']!r}"
            )

        if not isinstance(entry["reward_rules"], list):
            raise ValueError(f"Card '{label}': 'reward_rules' must be a list")

        aliases = reward_rule_aliases()
        for j, rule in enumerate(entry["reward_rules"]):
            missing_rule_keys = REQUIRED_RULE_KEYS - rule.keys()
            if missing_rule_keys:
                raise ValueError(
                    f"Card '{label}', rule {j} is missing required fields: {missing_rule_keys}"
                )
            try:
                Decimal(rule["reward_rate"])
            except (InvalidOperation, TypeError):
                raise ValueError(
                    f"Card '{label}', rule '{rule.get('category', j)}': "
                    f"'reward_rate' is not a valid decimal: {rule['reward_rate']!r}"
                )
            # Unmapped labels would ingest fine and then never match any spend,
            # so refuse them here rather than scoring the card as if the rule
            # did not exist.
            if rule["category"] not in aliases:
                raise ValueError(
                    f"Card '{label}', rule '{rule['category']}': category is not in "
                    f"reward_rule_aliases.json — add it there, mapping to a rewards "
                    f"category or to null if it should not be scored"
                )

        # A card with no welcome bonus has no threshold and no window to meet.
        has_bonus = Decimal(entry["signup_bonus"]) > 0
        required = entry["signup_bonus_required_spending"]
        months = entry["signup_bonus_spend_period_months"]

        if has_bonus:
            try:
                Decimal(required)
            except (InvalidOperation, TypeError):
                raise ValueError(
                    f"Card '{label}': 'signup_bonus_required_spending' is not a valid "
                    f"decimal: {required!r}"
                )
            if not isinstance(months, int) or isinstance(months, bool) or months < 1:
                raise ValueError(
                    f"Card '{label}': 'signup_bonus_spend_period_months' is not a valid "
                    f"integer: {months!r}"
                )
        else:
            if required is not None:
                try:
                    Decimal(required)
                except (InvalidOperation, TypeError):
                    raise ValueError(
                        f"Card '{label}': 'signup_bonus_required_spending' must be null "
                        f"or a decimal when there is no signup bonus: {required!r}"
                    )
            if months is not None and (
                not isinstance(months, int) or isinstance(months, bool) or months < 0
            ):
                raise ValueError(
                    f"Card '{label}': 'signup_bonus_spend_period_months' must be null "
                    f"or a non-negative integer when there is no signup bonus: {months!r}"
                )



@transaction.atomic
def ingest_card_catalog():
    card_data = load_card_catalog()
    _validate_catalog(card_data)

    cards_created = 0
    cards_updated = 0
    rules_created = 0
    rules_updated = 0
    rules_deleted = 0

    processed_card_ids = set()

    for card_product in card_data:
        card_obj, created = Card_Products.objects.update_or_create(
            name=card_product["name"],
            issuer=card_product["issuer"],
            defaults={
                "network": card_product["network"],
                "card_type": card_product["card_type"],
                "annual_fee": card_product["annual_fee"],
                "base_reward_rate": card_product["base_reward_rate"],
                "signup_bonus": card_product["signup_bonus"],
                # Validation guarantees these are only null when there is no
                # bonus, in which case scoring short-circuits before reading them.
                "signup_bonus_required_spending": (
                    card_product["signup_bonus_required_spending"] or 0
                ),
                "is_active": True,  # re-activates card previously inactive
                "is_catalog": True,
                "signup_bonus_spend_period_months": (
                    card_product["signup_bonus_spend_period_months"] or 0
                ),
                "reward_currency": card_product["signup_bonus_unit"],
            }
        )
        if created:
            cards_created += 1
        else:
            cards_updated += 1

        processed_card_ids.add(card_obj.id)

        #reward rules: upsert what's in the snapshot
        snapshot_categories = set()
        for rule in card_product["reward_rules"]:
            _,  rule_created = Reward_Rules.objects.update_or_create(
                card_product=card_obj,
                category=rule["category"],
                defaults={
                    "reward_unit": rule["reward_unit"],
                    "reward_rate": rule["reward_rate"],
                }
            )
            if rule_created:
                rules_created += 1
            else:
                rules_updated += 1
            snapshot_categories.add(rule["category"])

        # delete any category this card no longer has in the snapshot
        # safe to hard-delete: Transactions does not FK to Reward_Rules
        stale = Reward_Rules.objects.filter(card_product=card_obj).exclude(
            category__in=snapshot_categories
        )
        deleted_count, _ = stale.delete()
        rules_deleted += deleted_count

    #mark anything NOT in this snapshot as inactive
    # soft-delete (is_active=False) rather than hard-delete because User_cards may reference these rows
    cards_deactivated = Card_Products.objects.filter(is_active=True).exclude(
        id__in=processed_card_ids
    ).update(is_active=False)

    return {
        "cards_created": cards_created,
        "cards_updated": cards_updated,
        "cards_deactivated": cards_deactivated,
        "rules_created": rules_created,
        "rules_updated": rules_updated,
        "rules_deleted": rules_deleted,
    }
