from django.db import models
from apps.uploads.models import Uploads
from apps.users.models import User_cards
# Create your models here.
class MCC_Codes(models.Model):
    code = models.CharField(primary_key=True, max_length=255)
    category = models.CharField(max_length=255)
    merchant_name = models.CharField(max_length=255, blank=True, default='')
class Transactions(models.Model):
    class Meta:
        # ensures no two transactions have the same upload and row_index
        unique_together= ('upload', 'row_index')
    upload = models.ForeignKey(Uploads, on_delete = models.CASCADE,related_name = "upload_transactions")
    user_card = models.ForeignKey(User_cards, on_delete = models.CASCADE,related_name = "user_card_transactions")
    # null=True lets a row with an unrecognized MCC be stored uncategorized rather than rejected;
    # PROTECT still blocks deleting an MCC_Code that IS referenced by a transaction
    mcc_code = models.ForeignKey(MCC_Codes, on_delete = models.PROTECT, null = True, blank = True, related_name = "mcc_code_transactions")
    # sign convention: positive = spend, negative = cash-back / refund / statement credit
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    row_index = models.PositiveIntegerField()


# Phase 3 — durable L2 cache for merchant -> MCC resolutions.
# Anything the LLM ever resolves is stored here so you never pay for the same
# merchant twice (Redis is the volatile L1 in front of this).
# TODO: add the fields, then `makemigrations transactions` + `migrate`.
class MerchantResolution(models.Model):
    merchant_key = models.CharField(primary_key=True, max_length=255)
    mcc_code = models.ForeignKey(MCC_Codes, on_delete=models.PROTECT, null=True, blank=True)
    category = models.CharField(max_length=32, blank=True, default="")
    source = models.CharField(max_length=16)   # 'rule',  'llm' or 'manual'
    confidence = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
