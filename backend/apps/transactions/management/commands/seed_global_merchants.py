"""
Seed (or refresh) GlobalMerchantAlias from data/card_catalog/global_merchant_aliases.json.

Usage:
    python manage.py seed_global_merchants          # upsert all entries
    python manage.py seed_global_merchants --clear  # wipe table first, then upsert

Run this after migrate to have the global tier available on the first upload.
Re-run it whenever the JSON file is updated.
"""

import json
import os

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.transactions.models import GlobalMerchantAlias
from services.category_resolver import invalidate_global_alias_cache, is_valid_category

ALIASES_PATH = os.path.join(
    settings.BASE_DIR, "data", "card_catalog", "global_merchant_aliases.json"
)


class Command(BaseCommand):
    help = "Seed GlobalMerchantAlias from global_merchant_aliases.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing GlobalMerchantAlias rows before seeding.",
        )

    def handle(self, *args, **options):
        with open(ALIASES_PATH) as f:
            entries = json.load(f)

        if not isinstance(entries, list):
            self.stderr.write("global_merchant_aliases.json must be a JSON array.")
            return

        if options["clear"]:
            count = GlobalMerchantAlias.objects.all().delete()[0]
            self.stdout.write(f"Cleared {count} existing rows.")

        created = updated = skipped = 0
        errors = []

        for entry in entries:
            key = (entry.get("merchant_key") or "").strip()
            name = (entry.get("canonical_name") or "").strip()
            category = (entry.get("category") or "").strip()

            if not key or not category:
                errors.append(f"Skipped: missing merchant_key or category in {entry!r}")
                continue

            if not is_valid_category(category):
                errors.append(
                    f"Skipped {key!r}: {category!r} is not a valid rewards category."
                )
                continue

            _obj, was_created = GlobalMerchantAlias.objects.update_or_create(
                merchant_key=key,
                defaults={"canonical_name": name, "category": category},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        for msg in errors:
            self.stderr.write(self.style.WARNING(msg))
            skipped += 1

        # Drop the in-process cache so the next resolve picks up new rows.
        invalidate_global_alias_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — created: {created}, updated: {updated}, skipped: {skipped}."
            )
        )
