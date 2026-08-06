from apps.cards.models import Card_Products
from services.category_resolver import reward_categories


def _card_passes_gate(card, known_categories: frozenset) -> bool:
    if not card.name or not card.issuer or card.is_active is False:
        return False # card has no name, no issuer, or is inactive 
    rules = list(card.reward_rules.all())

    if len(rules) == 0 and card.base_reward_rate == 0:
        return False # no reward rules or base reward rate
    for rule in rules:
        if rule.reward_rate <= 0:
            return False # rewarde rate cannot be negatgive
        if rule.category not in known_categories:
            return False # category not in known categories
    return True

def get_valid_cards() -> list:
    known_categories = reward_categories()
    return [
        c for c in Card_Products.objects
            .filter(is_active=True, is_catalog=True)
            .prefetch_related("reward_rules")
        if _card_passes_gate(c, known_categories)
    ]