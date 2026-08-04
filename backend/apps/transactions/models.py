from django.db import models

from apps.uploads.models import Uploads
from apps.users.models import CustomUser, User_cards

UNRESOLVED_CATEGORY = ""

# resolution_source values — the tier that produced the category
SOURCE_USER = "user"      # user's own override (tier 1/2)
SOURCE_GLOBAL = "global"  # admin-curated GlobalMerchantAlias (tier 3)
SOURCE_BANK = "bank"      # adapter's bank category (tier 4)
SOURCE_NONE = ""          # genuinely unresolved or categorizedto "other"


class Transactions(models.Model):
    class Meta:
        unique_together = ('upload', 'row_index')

    upload = models.ForeignKey(Uploads, on_delete=models.CASCADE, related_name="upload_transactions")
    user_card = models.ForeignKey(User_cards, on_delete=models.CASCADE, related_name="user_card_transactions")

    # this is the rewards category - it is "" when it needs user review
    category = models.CharField(max_length=32, blank=True, default=UNRESOLVED_CATEGORY)

    # this is an opqau comparison key (UPPERCASE). Used to key overrides and backfills
    merchant_key = models.CharField(max_length=255, blank=True, default="", db_index=True)

    # Human-readable version of merchant_key (title-cased) Shown prominently
    # in the review queue alongside the raw description
    normalized_description = models.CharField(max_length=255, blank=True, default="")

    # labels the tier that categorized the transaction
    resolution_source = models.CharField(max_length=16, blank=True, default=SOURCE_NONE)

    # 0.0–1.0: user=1.0, global=0.9, bank=0.7, unresolved=0.0
    confidence = models.FloatField(default=0.0)

    # sign convention: positive = spend, negative = refund / credit
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)  # raw description string from the full bank transaction
    row_index = models.PositiveIntegerField()


class MerchantResolution(models.Model):
    """
    A user's own answer for "what category is this merchant?".

    Scoped per user: a global table would let one person's label rewrite
    categorization for everybody. Admin-curated data resides in
    GlobalMerchantAlias.
    """
    class Meta:
        unique_together = ('user', 'merchant_key')

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="merchant_resolutions")
    merchant_key = models.CharField(max_length=255)
    category = models.CharField(max_length=32)
    source = models.CharField(max_length=16, default="user")  # 'user' | 'admin'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GlobalMerchantAlias(models.Model):
    """
    Admin-curated merchant knowledge (tier 3 in the resolver).

    Loaded from data/card_catalog/global_merchant_aliases.json via the
    seed_global_merchants management command. 
    
    Keys match what merchant_key()
    produces so a transaction is matched without any additional lookup.

    This is intentionally separate from MerchantResolution: a wrong entry here
    affects every user, so it needs a different write path (admin command,
    not a POST from a regular user).
    """
    merchant_key = models.CharField(max_length=255, unique=True, db_index=True)
    canonical_name = models.CharField(max_length=255)  # pretty name for display
    category = models.CharField(max_length=32)

    class Meta:
        verbose_name_plural = "global merchant aliases"

    def __str__(self):
        return f"{self.canonical_name} ({self.merchant_key}) → {self.category}"
