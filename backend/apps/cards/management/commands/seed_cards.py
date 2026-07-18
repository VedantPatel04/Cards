from django.core.management.base import BaseCommand

from services.card_catalog_ingestion import ingest_card_catalog


class Command(BaseCommand):
    help = "Loads card_catalog.json snapshot into Card_Products + Reward_Rules (idempotent)"

    def handle(self, *args, **kwargs):
        try:
            summary = ingest_card_catalog()
        except (ValueError, FileNotFoundError) as exc:
            # validation errors and missing file are caught here and shown cleanly,
            # not as a raw traceback — nothing was written to the DB (atomic rollback)
            self.stderr.write(self.style.ERROR(f"Ingestion aborted: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Done — "
            f"cards: {summary['cards_created']} created, "
            f"{summary['cards_updated']} updated, "
            f"{summary['cards_deactivated']} deactivated | "
            f"rules: {summary['rules_created']} created, "
            f"{summary['rules_updated']} updated, "
            f"{summary['rules_deleted']} deleted"
        ))
