from django.db import models

# Create your models here.

class Card_Products(models.Model):
    name = models.CharField(max_length = 255)
    issuer = models.CharField(max_length = 255)
    network = models.CharField(max_length = 255)
    card_type = models.CharField(max_length = 255)
    is_active = models.BooleanField(default = True)
    # True = seeded/recommendable catalog product
    # False -> reserved for future non-catalog wallet cards 
    is_catalog = models.BooleanField(default = True)

    annual_fee = models.DecimalField(max_digits = 10, decimal_places = 2)
    base_reward_rate = models.DecimalField(max_digits = 10, decimal_places = 2)
    signup_bonus = models.DecimalField(max_digits = 10, decimal_places = 2)
    # below field used to calculate signup_bonus score defines min amnt of spending required to earn rewards
    signup_bonus_required_spending = models.DecimalField(max_digits = 10, decimal_places = 2)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    signup_bonus_spend_period_months = models.PositiveIntegerField(default = 3)
    # The currency this card earns in. Points/miles are counts, not dollars, scoring converts them with POINT_VALUE_CENTS before comparing cards
    reward_currency = models.CharField(max_length = 32, default = "cash_back")
    class Meta:
       unique_together = ('name', 'issuer') 

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

