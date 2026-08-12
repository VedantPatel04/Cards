from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

from apps.cards.models import Card_Products


class CustomUserManager(UserManager):
    """
    AbstractUser's default manager always passes email= into the model
    constructor. With email removed from CustomUser, that raises TypeError —
    so create paths must omit it.
    """

    def _create_user_object(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError("The given username must be set")
        # Lookup the real model class from the global app registry so this
        # manager method can be used in migrations (same pattern as Django).
        GlobalUserModel = apps.get_model(
            self.model._meta.app_label, self.model._meta.object_name
        )
        username = GlobalUserModel.normalize_username(username)
        user = self.model(username=username, **extra_fields)
        user.password = make_password(password)
        return user


class CustomUser(AbstractUser):
    """
    Username + password auth only.

    AbstractUser defines an email field; assigning None removes it from this
    concrete model so we do not collect unused PII. createsuperuser must not
    prompt for email — REQUIRED_FIELDS is empty.
    """

    email = None
    REQUIRED_FIELDS = []
    objects = CustomUserManager()


class User_cards(models.Model):
    class Meta:
        unique_together = ("user", "card")

    card = models.ForeignKey(
        Card_Products, on_delete=models.CASCADE, related_name="user_card"
    )
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="user"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
