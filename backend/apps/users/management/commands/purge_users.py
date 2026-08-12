"""
Purge disposable / probe user accounts and all cascaded owned data.

Safe by default: dry-run mode, never touches staff/superuser unless forced,
and requires an explicit match strategy.

Examples:

    # Preview default probe-style prefixes
    python manage.py purge_users --dry-run

    # Delete accounts matching probe_/priv_/lim_ prefixes (non-staff only)
    python manage.py purge_users --yes

    # Custom prefixes + age filter
    python manage.py purge_users --prefix test_ --older-than-days 7 --dry-run

    # Exact usernames
    python manage.py purge_users --username alice --username bob --yes

    # Everything non-staff (dangerous)
    python manage.py purge_users --all-non-staff --dry-run
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.cards.models import Card_Products
from apps.transactions.models import MerchantResolution, Transactions
from apps.uploads.models import Uploads
from apps.users.models import User_cards
from services.merchant_cache import cache_delete_user

User = get_user_model()

DEFAULT_PREFIXES = ("probe_", "priv_", "lim_")


class Command(BaseCommand):
    help = "Hard-delete matched user accounts and cascaded owned data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show matches and owned-row counts without deleting.",
        )
        parser.add_argument(
            "--prefix",
            action="append",
            dest="prefixes",
            default=None,
            help=(
                "Username prefix to match (repeatable). "
                f"Default when no other match flags: {', '.join(DEFAULT_PREFIXES)}"
            ),
        )
        parser.add_argument(
            "--username",
            action="append",
            dest="usernames",
            default=None,
            help="Exact username to delete (repeatable).",
        )
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=None,
            help="Only users whose date_joined is at least N days ago.",
        )
        parser.add_argument(
            "--all-non-staff",
            action="store_true",
            help="Match every non-staff, non-superuser account.",
        )
        parser.add_argument(
            "--include-staff",
            action="store_true",
            help="Allow matching is_staff users (still never matches superusers).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required to actually delete (skipped for --dry-run).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefixes = options["prefixes"]
        usernames = options["usernames"] or []
        older_than = options["older_than_days"]
        all_non_staff = options["all_non_staff"]
        include_staff = options["include_staff"]

        using_defaults = False
        if not prefixes and not usernames and not all_non_staff:
            prefixes = list(DEFAULT_PREFIXES)
            using_defaults = True
        prefixes = prefixes or []

        qs = User.objects.filter(is_superuser=False).order_by("id")
        if not include_staff:
            qs = qs.filter(is_staff=False)

        if all_non_staff and not prefixes and not usernames:
            # Full non-staff sweep — qs already scoped.
            pass
        else:
            match_q = Q()
            for prefix in prefixes:
                match_q |= Q(username__istartswith=prefix)
            if usernames:
                match_q |= Q(username__in=usernames)
            if not match_q:
                raise CommandError("No match strategy provided.")
            qs = qs.filter(match_q)

        if older_than is not None:
            if older_than < 0:
                raise CommandError("--older-than-days must be >= 0.")
            cutoff = timezone.now() - timedelta(days=older_than)
            qs = qs.filter(date_joined__lte=cutoff)

        users = list(qs)
        if using_defaults:
            self.stdout.write(
                f"Using default prefixes: {', '.join(DEFAULT_PREFIXES)}"
            )

        if not users:
            self.stdout.write(self.style.SUCCESS("No matching users."))
            return

        self.stdout.write(f"Matched {len(users)} user(s):")
        for user in users:
            wallets = User_cards.objects.filter(user=user).count()
            uploads = Uploads.objects.filter(user=user).count()
            txs = Transactions.objects.filter(user_card__user=user).count()
            labels = MerchantResolution.objects.filter(user=user).count()
            customs = Card_Products.objects.filter(
                owner=user, is_catalog=False
            ).count()
            self.stdout.write(
                f"  id={user.pk} username={user.username!r} "
                f"joined={user.date_joined.date()} "
                f"[wallets={wallets} uploads={uploads} txs={txs} "
                f"labels={labels} custom_cards={customs}]"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "Dry run only. Re-run without --dry-run (and with --yes) to delete."
            ))
            return

        if not options["yes"]:
            self.stdout.write(self.style.WARNING(
                "Refusing to delete without --yes."
            ))
            return

        deleted_names = []
        for user in users:
            user_id = user.pk
            deleted_names.append(user.username)
            user.delete()
            cache_delete_user(user_id)

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {len(deleted_names)} user(s): {', '.join(deleted_names)}"
        ))
