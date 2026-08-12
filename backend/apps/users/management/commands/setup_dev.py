"""
One-shot local setup for Postman / manual testing.

    python manage.py setup_dev

Seeds the card catalog + global merchant aliases, ensures the demo user
exists, attaches the first catalog card to their wallet if empty, and prints
credentials + user_card_id.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.cards.models import Card_Products
from apps.users.models import User_cards

User = get_user_model()

DEMO_USERNAME = "user1"
DEMO_PASSWORD = "user1Password"


class Command(BaseCommand):
    help = "Seed catalog/aliases and ensure demo user1 has a wallet card."

    def handle(self, *args, **options):
        self.stdout.write("Seeding card catalog…")
        call_command("seed_cards")

        self.stdout.write("Seeding global merchant aliases…")
        call_command("seed_global_merchants")

        user, created = User.objects.get_or_create(username=DEMO_USERNAME)
        # Keep login credentials stable even if the user already existed.
        user.set_password(DEMO_PASSWORD)
        user.save()
        self.stdout.write(
            f"Demo user {'created' if created else 'updated'}: {DEMO_USERNAME}"
        )

        card = (
            Card_Products.objects.filter(is_active=True, is_catalog=True)
            .order_by("id")
            .first()
        )
        if card is None:
            self.stderr.write(self.style.ERROR(
                "No active catalog cards — seed_cards may have failed."
            ))
            return

        entry = User_cards.objects.filter(user=user, is_active=True).order_by("id").first()
        if entry is None:
            entry = User_cards.objects.create(user=user, card=card, is_active=True)
            self.stdout.write(
                f"Wallet: added {card.name} ({card.issuer}) as user_card_id={entry.pk}"
            )
        else:
            self.stdout.write(
                f"Wallet: already has user_card_id={entry.pk} "
                f"({entry.card.name} / {entry.card.issuer})"
            )

        self.stdout.write(self.style.SUCCESS(
            "\n".join([
                "Ready for Postman:",
                f"  username:     {DEMO_USERNAME}",
                f"  password:     {DEMO_PASSWORD}",
                f"  user_card_id: {entry.pk}",
            ])
        ))
