"""
process_upload / ingest_transactions tests.

Covers idempotency (bulk re-run), resolution dedup, new summary fields
(coverage_pct, needs_review), and the stored merchant/resolution fields.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

import seeds
import services.category_resolver as resolver_module
from apps.transactions.models import (
    SOURCE_BANK,
    SOURCE_USER,
    UNRESOLVED_CATEGORY,
    GlobalMerchantAlias,
    Transactions,
)
from services.category_resolver import invalidate_global_alias_cache
from services.merchant_normalize import merchant_key, normalized_display
from services.upload_pipeline import process_upload


def _csv(*lines: str) -> bytes:
    header = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo"
    return ("\n".join((header, *lines)) + "\n").encode("utf-8")


class PipelineTestCase(TestCase):
    def setUp(self):
        resolver_module._reward_categories = None
        invalidate_global_alias_cache()
        self.user_card = seeds.make_user_card()
        self.upload = seeds.make_upload(user=self.user_card.user, status="pending")
        self._patch(patch.object(resolver_module, "cache_get", return_value=None))
        self._patch(patch.object(resolver_module, "cache_set"))

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)


class ProcessUploadIdempotencyTests(PipelineTestCase):
    FILE = _csv(
        "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,",
        "07/08/2026,07/10/2026,MTA*NYCT PAYGO,Travel,Sale,-3.00,",
        "07/08/2026,07/10/2026,MTA*NYCT PAYGO,Travel,Sale,-3.00,",
        "07/06/2026,07/06/2026,FOREIGN TRANSACTION FEE,Fees & Adjustments,Fee,-0.99,",
    )

    def test_second_run_updates_in_place_using_bulk_write(self):
        first = process_upload(self.upload, self.user_card, self.FILE)
        self.assertEqual(first["created"], 4)
        self.assertEqual(first["updated"], 0)
        self.assertEqual(first["merchants"], 3)

        snapshot = list(
            Transactions.objects.filter(upload=self.upload)
            .order_by("row_index")
            .values_list("row_index", "description", "amount", "category")
        )
        second = process_upload(self.upload, self.user_card, self.FILE)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 4)
        self.assertEqual(
            snapshot,
            list(
                Transactions.objects.filter(upload=self.upload)
                .order_by("row_index")
                .values_list("row_index", "description", "amount", "category")
            ),
        )

    def test_amount_sign_and_category_from_adapter(self):
        process_upload(self.upload, self.user_card, self.FILE)
        walmart = Transactions.objects.get(upload=self.upload, description="WAL-MART #2297")
        self.assertEqual(walmart.amount, Decimal("35.34"))
        self.assertEqual(walmart.category, "groceries")

        fee = Transactions.objects.get(
            upload=self.upload, description="FOREIGN TRANSACTION FEE"
        )
        self.assertEqual(fee.category, "other")

    def test_merchant_key_and_normalized_description_stored(self):
        process_upload(self.upload, self.user_card, self.FILE)
        walmart = Transactions.objects.get(upload=self.upload, description="WAL-MART #2297")
        self.assertEqual(walmart.merchant_key, merchant_key("WAL-MART #2297"))
        self.assertEqual(walmart.normalized_description, normalized_display("WAL-MART #2297"))

    def test_resolution_source_and_confidence_stored(self):
        process_upload(self.upload, self.user_card, self.FILE)
        walmart = Transactions.objects.get(upload=self.upload, description="WAL-MART #2297")
        self.assertEqual(walmart.resolution_source, SOURCE_BANK)
        self.assertAlmostEqual(walmart.confidence, 0.7)

    def test_coverage_pct_in_summary(self):
        summary = process_upload(self.upload, self.user_card, self.FILE)
        self.assertIn("coverage_pct", summary)
        self.assertGreater(summary["coverage_pct"], 0)

    def test_resolution_deduped_per_merchant(self):
        """Six identical rows must not cost six Redis/DB round trips."""
        with patch.object(resolver_module, "cache_get", return_value=None) as mock_get:
            process_upload(self.upload, self.user_card, self.FILE)
        self.assertEqual(mock_get.call_count, 3)


class UnresolvedRowTests(PipelineTestCase):
    def test_unknown_chase_category_goes_to_review_queue(self):
        file_bytes = _csv(
            "07/16/2026,07/17/2026,MYSTERY VENDOR 44,Sponsorships,Sale,-10.00,",
        )
        summary = process_upload(self.upload, self.user_card, file_bytes)
        self.assertEqual(summary["needs_review"], 1)
        self.assertLess(summary["coverage_pct"], 100)
        tx = Transactions.objects.get(upload=self.upload)
        self.assertEqual(tx.category, UNRESOLVED_CATEGORY)

    def test_blank_category_credit_is_other(self):
        file_bytes = _csv("07/16/2026,07/17/2026,Payment Thank You,,Payment,1500.00,")
        summary = process_upload(self.upload, self.user_card, file_bytes)
        self.assertEqual(summary["needs_review"], 0)
        self.assertEqual(summary["coverage_pct"], 100.0)

    def test_global_alias_resolves_unknown_prevents_review(self):
        """GlobalMerchantAlias at tier 3 keeps rows out of the review queue."""
        GlobalMerchantAlias.objects.create(
            merchant_key="MYSTERY VENDOR",
            canonical_name="Mystery Vendor",
            category="entertainment",
        )
        invalidate_global_alias_cache()
        file_bytes = _csv(
            "07/16/2026,07/17/2026,MYSTERY VENDOR 44,Sponsorships,Sale,-10.00,",
        )
        summary = process_upload(self.upload, self.user_card, file_bytes)
        self.assertEqual(summary["needs_review"], 0)
        tx = Transactions.objects.get(upload=self.upload)
        self.assertEqual(tx.category, "entertainment")
        self.assertEqual(tx.resolution_source, "global")

    def test_user_override_beats_bank_category(self):
        """User's saved answer (confidence 1.0) overrides the bank label (0.7)."""
        key = merchant_key("WAL-MART #2297")
        seeds.make_merchant_resolution(
            user=self.user_card.user, merchant_key=key, category="shopping"
        )
        file_bytes = _csv("07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,")
        process_upload(self.upload, self.user_card, file_bytes)
        tx = Transactions.objects.get(upload=self.upload)
        self.assertEqual(tx.category, "shopping")
        self.assertEqual(tx.resolution_source, SOURCE_USER)
        self.assertAlmostEqual(tx.confidence, 1.0)
