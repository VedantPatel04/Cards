from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.
class CustomUser(AbstractUser):
    # the following 3 fields are intialized by default by AbstractUser
    #password = models.CharField(max_length = 255)
    #id = models.AutoField(primary_key = True)
    #username = models.CharField(max_length = 255, unique = True)

    email = models.EmailField(unique = True, blank = False)

    


