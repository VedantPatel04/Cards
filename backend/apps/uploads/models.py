from django.db import models
from apps.users.models import CustomUser
# Create your models here.
class Uploads(models.Model):
    class Meta:
        unique_together = ('user', 'file_hash')
    user = models.ForeignKey(CustomUser, on_delete = models.CASCADE,related_name = "user_uploads")
    status = models.CharField(max_length = 255)
    filename = models.CharField(max_length = 255)
    file_hash = models.CharField(max_length = 255)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)