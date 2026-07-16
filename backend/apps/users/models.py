from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.cards.models import Card_Products
# Create your models here.
class CustomUser(AbstractUser):
    # the following 3 fields are intialized by default by AbstractUser
    #password = models.CharField(max_length = 255)
    #id = models.AutoField(primary_key = True)
    #username = models.CharField(max_length = 255, unique = True)

    email = models.EmailField(unique = True, blank = False)

class User_cards(models.Model):
    class Meta:
        unique_together = ('user','card')
    card = models.ForeignKey(Card_Products, on_delete = models.CASCADE, related_name = "user_card")
    user = models.ForeignKey(CustomUser, on_delete = models.CASCADE, related_name = "user")
    created_at = models.DateTimeField(auto_now_add = True)
    is_active = models.BooleanField(default = True)

