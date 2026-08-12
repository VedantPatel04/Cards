from django.conf import settings
from django.db import models


class Card_Products(models.Model):
    name = models.CharField(max_length=255)
    issuer = models.CharField(max_length=255)
    network = models.CharField(max_length=255)
    card_type = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    # True = seeded/recommendable catalog product (owner must be null)
    # False = user-created wallet card (owner must be set)
    is_catalog = models.BooleanField(default=True)
    # Catalog rows: null. Custom rows: the creating user. CASCADE so account
    # deletion removes that user's custom products.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="owned_card_products",
    )

    annual_fee = models.DecimalField(max_digits=10, decimal_places=2)
    base_reward_rate = models.DecimalField(max_digits=10, decimal_places=2)
    signup_bonus = models.DecimalField(max_digits=10, decimal_places=2)
    # min spend required to earn signup bonus (scoring)
    signup_bonus_required_spending = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signup_bonus_spend_period_months = models.PositiveIntegerField(default=3)
    # Points/miles are counts, not dollars; scoring converts via POINT_VALUE_CENTS
    reward_currency = models.CharField(max_length=32, default="cash_back")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "issuer"],
                condition=models.Q(owner__isnull=True),
                name="cards_catalog_name_issuer_uniq",
            ),
            models.UniqueConstraint(
                fields=["name", "issuer", "owner"],
                condition=models.Q(owner__isnull=False),
                name="cards_custom_name_issuer_owner_uniq",
            ),
        ] 

class Reward_Rules(models.Model):# related_name param allows for lookup of reward_rule objects 
                                                    # using Card_Products_A.reward_rules.all()
    class Meta:
        unique_together = ('card_product', 'category') # ensures no two rows in the table are the same
    card_product = models.ForeignKey(Card_Products, on_delete = models.CASCADE, related_name = "reward_rules")
    category = models.CharField(max_length = 255)
    reward_unit = models.CharField(max_length = 255)
    reward_rate = models.DecimalField(max_digits = 10, decimal_places = 2)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)

