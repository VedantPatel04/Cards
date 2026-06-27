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
    # prevents deletion of an MCC_Code that is referenced by a transaction
    mcc_code = models.ForeignKey(MCC_Codes, on_delete = models.PROTECT,related_name = "mcc_code_transactions")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    row_index = models.PositiveIntegerField()
    