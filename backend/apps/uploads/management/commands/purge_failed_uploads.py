"""
Purge Uploads rows that failed (or were abandoned) and have no transactions.

    python manage.py purge_failed_uploads --dry-run
    python manage.py purge_failed_uploads

Current ingest deletes failed shells immediately; this cleans leftovers from
older builds (status=failed) and any zero-tx pending/failed shells.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.uploads.models import Uploads


class Command(BaseCommand):
    help = "Delete upload shells with no transactions (failed/pending leftovers)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List matching uploads without deleting them.",
        )
        parser.add_argument(
            "--include-processed",
            action="store_true",
            help=(
                "Also delete status=processed/completed uploads that somehow "
                "have zero transactions (empty shells)."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        statuses = ["failed", "pending"]
        if options["include_processed"]:
            statuses.extend(["processed", "completed"])

        qs = (
            Uploads.objects.annotate(tx_count=Count("upload_transactions"))
            .filter(tx_count=0)
            .filter(status__in=statuses)
            .order_by("id")
        )

        rows = list(qs.values("id", "user_id", "filename", "status", "created_at"))
        if not rows:
            self.stdout.write(self.style.SUCCESS("No empty failed/pending uploads found."))
            return

        for row in rows:
            self.stdout.write(
                f"  id={row['id']} user_id={row['user_id']} "
                f"status={row['status']!r} file={row['filename']!r} "
                f"created={row['created_at']}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"Dry run: would delete {len(rows)} upload(s). Re-run without --dry-run."
            ))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} upload row(s)."))
