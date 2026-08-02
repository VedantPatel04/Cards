"""
Run the Chase sample CSV through process_upload twice and print the ladder.

Usage (from backend/):
  python manage.py demo_upload
  python manage.py demo_upload --clear   # wipe prior demo MerchantResolutions + txs

Shows the tier used to resolve each distinct merchant: Redis/DB/LLM/Tier-5 path, then a second
pass that should make zero LLM calls.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

import redis
from django.conf import settings
from django.core.management.base import BaseCommand

import services.mcc_resolver as resolver_module
from apps.transactions.models import MCC_Codes, MerchantResolution, Transactions
from apps.uploads.models import Uploads
from services.csv_parser import normalize_csv
from services.merchant_cache import cache_get
from services.merchant_normalize import merchant_key
from services.upload_pipeline import process_upload

SAMPLE = Path(settings.BASE_DIR) / "data" / "sample_uploads" / "Chase Transaction Statement.csv"


class _TierTraceFilter(logging.Filter):
    """Keep only mcc_resolver DEBUG lines so the demo stays readable."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("services.mcc_resolver")


class Command(BaseCommand):
    help = "Demo: process Chase sample CSV twice with resolver tier tracing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete prior demo upload rows / MerchantResolutions for sample keys first.",
        )
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Force LLM off for this run (Tier 5 fallback only on cold miss).",
        )

    def handle(self, *args, **options):
        if not SAMPLE.is_file():
            self.stderr.write(self.style.ERROR(f"Sample CSV not found: {SAMPLE}"))
            return

        self._configure_logging()
        self._print_env(force_no_llm=options["no_llm"])
        redis_ok = self._probe_redis()

        if options["no_llm"]:
            settings.LLM_ENABLED = False

        # Fresh memo so an empty merchant_rules.json is what we actually use.
        resolver_module.merchant_rules = None
        resolver_module.known_mcc_codes_cache = None

        mcc_count = MCC_Codes.objects.count()
        if mcc_count == 0:
            self.stdout.write(self.style.WARNING(
                "MCC_Codes is empty — run: python manage.py seed_mcc"
            ))
            return
        self.stdout.write(f"MCC_Codes seeded: {mcc_count} rows")
        self.stdout.write(f"merchant_rules.json entries: {len(resolver_module._load_merchant_rules())}")

        file_bytes = SAMPLE.read_bytes()
        rows = normalize_csv(file_bytes)
        distinct = {}
        for row in rows:
            key = merchant_key(row["raw_description"])
            distinct.setdefault(key, row)

        if options["clear"]:
            self._clear_demo_state(list(distinct))

        self._print_preflight(distinct, redis_ok)

        user, user_card = self._demo_wallet()
        upload, _ = Uploads.objects.update_or_create(
            user=user,
            file_hash="demo-chase-sample",
            defaults={"filename": SAMPLE.name, "status": "pending"},
        )

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== RUN 1 (cold / warm path) ==="))
        summary1 = process_upload(upload, user_card, file_bytes)
        self._print_summary("run1", summary1)
        self._print_transactions(upload)
        self._print_resolutions(list(distinct))
        if redis_ok:
            self._print_redis_keys(list(distinct))

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== RUN 2 (must be cache/DB only) ==="))
        summary2 = process_upload(upload, user_card, file_bytes)
        self._print_summary("run2", summary2)
        self._print_transactions(upload)

        if summary2["llm_calls"] != 0:
            self.stdout.write(self.style.ERROR(
                f"FAIL: second run made {summary2['llm_calls']} LLM call(s); expected 0"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "OK: second run made 0 LLM calls (Redis and/or MerchantResolution hit)."
            ))

        if summary1["created"] and summary2["updated"] != summary1["rows"]:
            self.stdout.write(self.style.WARNING(
                "Note: expected run2 to update every row from run1."
            ))

    def _demo_wallet(self):
        """A stable demo user + card, so re-runs land on the same upload row."""
        from django.contrib.auth import get_user_model
        from apps.cards.models import Card_Products
        from apps.users.models import User_cards

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username="demo_upload_user",
            defaults={"email": "demo_upload@example.com"},
        )
        if created:
            user.set_password("demo")
            user.save()

        card, _ = Card_Products.objects.get_or_create(
            name="Demo Card",
            issuer="Demo Issuer",
            defaults={
                "network": "Visa",
                "card_type": "credit",
                "annual_fee": Decimal("0.00"),
                "base_reward_rate": Decimal("1.00"),
                "signup_bonus": Decimal("0.00"),
                "signup_bonus_required_spending": Decimal("0.00"),
            },
        )
        user_card, _ = User_cards.objects.get_or_create(user=user, card=card)
        return user, user_card

    def _configure_logging(self):
        handler = logging.StreamHandler(self.stdout)
        handler.setLevel(logging.DEBUG)
        handler.addFilter(_TierTraceFilter())
        handler.setFormatter(logging.Formatter("  [resolver] %(message)s"))
        root = logging.getLogger("services.mcc_resolver")
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        root.propagate = False

    def _print_env(self, force_no_llm: bool):
        self.stdout.write(self.style.MIGRATE_HEADING("Environment"))
        self.stdout.write(f"  REDIS_URL={settings.REDIS_URL}")
        self.stdout.write(f"  MERCHANT_CACHE_TTL={settings.MERCHANT_CACHE_TTL}")
        self.stdout.write(f"  LLM_ENABLED={settings.LLM_ENABLED} (force_off={force_no_llm})")
        self.stdout.write(f"  LLM_MODEL={settings.LLM_MODEL}")
        self.stdout.write(f"  LLM_API_KEY set={bool(settings.LLM_API_KEY)}")
        self.stdout.write(f"  LLM_MAX_CALLS_PER_UPLOAD={settings.LLM_MAX_CALLS_PER_UPLOAD}")
        self.stdout.write(f"  sample={SAMPLE}")

    def _probe_redis(self) -> bool:
        self.stdout.write(self.style.MIGRATE_HEADING("\nRedis"))
        try:
            client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
            pong = client.ping()
            self.stdout.write(self.style.SUCCESS(f"  ping -> {pong}"))
            return True
        except redis.RedisError as exc:
            self.stdout.write(self.style.WARNING(
                f"  unreachable ({exc.__class__.__name__}: {exc})\n"
                "  Cache will FAIL OPEN (miss every time). Pipeline still works via DB + LLM/Tier5.\n"
                "  To enable Redis on macOS:\n"
                "    brew install redis && brew services start redis\n"
                "    redis-cli ping   # expect PONG\n"
                "  Or: docker run -d --name cards-redis -p 6379:6379 redis:7-alpine"
            ))
            return False

    def _clear_demo_state(self, keys: list[str]):
        deleted_res = MerchantResolution.objects.filter(merchant_key__in=keys).delete()
        Uploads.objects.filter(file_hash="demo-chase-sample").delete()
        self.stdout.write(f"Cleared prior demo state (resolutions delete={deleted_res})")
        try:
            client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
            for key in keys:
                client.delete(f"merchant:{key}")
            self.stdout.write(f"Cleared Redis keys for {len(keys)} merchants")
        except redis.RedisError:
            pass

    def _print_preflight(self, distinct: dict, redis_ok: bool):
        self.stdout.write(self.style.MIGRATE_HEADING("\nPreflight (per distinct merchant_key)"))
        for key, row in distinct.items():
            cached = cache_get(key) if redis_ok else None
            stored = MerchantResolution.objects.filter(merchant_key=key).first()
            rule = resolver_module._load_merchant_rules().get(key)
            self.stdout.write(
                f"  {key!r}\n"
                f"    raw={row['raw_description']!r} category={row['source_category']!r}\n"
                f"    tier2_rule={rule!r}  redis={cached!r}  db="
                f"{None if stored is None else stored.mcc_code_id!r}"
                f" (source={getattr(stored, 'source', None)!r})"
            )

    def _print_summary(self, label: str, summary: dict):
        self.stdout.write(f"\n{label} summary: {summary}")

    def _print_transactions(self, upload):
        self.stdout.write("\nTransactions:")
        for tx in Transactions.objects.filter(upload=upload).order_by("row_index"):
            self.stdout.write(
                f"  [{tx.row_index:02d}] {tx.description!r:40s} "
                f"amt={tx.amount} mcc={tx.mcc_code_id!r}"
            )

    def _print_resolutions(self, keys: list[str]):
        self.stdout.write("\nMerchantResolution rows written:")
        for row in MerchantResolution.objects.filter(merchant_key__in=keys).order_by("merchant_key"):
            self.stdout.write(
                f"  {row.merchant_key!r:26s} -> mcc={row.mcc_code_id!r:8s} "
                f"category={row.category!r:14s} source={row.source!r} "
                f"confidence={row.confidence}"
            )

    def _print_redis_keys(self, keys: list[str]):
        self.stdout.write("\nRedis after run1:")
        for key in keys:
            self.stdout.write(f"  merchant:{key} = {cache_get(key)!r}")
