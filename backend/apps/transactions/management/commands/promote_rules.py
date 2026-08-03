"""

Run this whenever you add or change an entry in merchant_rules.json. It
upserts each key into MerchantResolution with source="rule" / confidence=1.0
and warms Redis so the next upload hits Tier 2 or Tier 3a rather than
re-evaluating.

Usage:
    python manage.py promote_rules
    python manage.py promote_rules --dry-run   #<-- preview without writing
"""

from __future__ import annotations

from pathlib import Path

import redis
from django.conf import settings
from django.core.management.base import BaseCommand

import services.mcc_resolver as resolver_module
from apps.transactions.models import MCC_Codes, MerchantResolution
from services.merchant_cache import cache_set


class Command(BaseCommand):
    help = "Upsert merchant_rules.json into MerchantResolution as source='rule'."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be written without touching the DB or Redis.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # fresh load of merchant_rules
        resolver_module.merchant_rules = None
        rules = resolver_module._load_merchant_rules()

        if not rules:
            self.stdout.write(self.style.WARNING("merchant_rules.json is empty — nothing to promote."))
            return

        known = set(MCC_Codes.objects.values_list("code", flat=True))
        created_count = 0
        updated_count = 0
        skipped = []

        for merchant_key, mcc in rules.items():
            if mcc not in known:
                self.stdout.write(
                    self.style.ERROR(
                        f"  SKIP  {merchant_key!r} -> {mcc!r}  (not in MCC_Codes)"
                    )
                )
                skipped.append(merchant_key)
                continue

            action = "DRY-RUN"
            if not dry_run:
                _, created = MerchantResolution.objects.update_or_create(
                    merchant_key=merchant_key,
                    defaults={
                        "mcc_code_id": mcc,
                        "source": "rule",
                        "confidence": 1.0,
                        "category": (
                            MCC_Codes.objects.filter(code=mcc)
                            .values_list("category", flat=True)
                            .first()
                            or ""
                        ),
                    },
                )
                #Warm Redis
                cache_set(merchant_key, mcc)
                if created:
                    created_count += 1
                    action = "created"
                else:
                    updated_count += 1
                    action = "updated"

            self.stdout.write(f"  {action:8}  {merchant_key!r:30} -> {mcc}")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(rules) - len(skipped)} rule(s) would be written. "
                "Re-run without --dry-run to apply."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nDone: {created_count} created, {updated_count} updated, "
                f"{len(skipped)} skipped (bad MCC)."
            ))
