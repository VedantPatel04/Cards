"""
process_upload tests.

Covers the Phase 7/8 pipeline contracts that unit tests on resolve_mcc alone
cannot: per-upload LLM budget across many merchants, merchant dedupe, and
idempotent re-processing of the same file bytes.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

import seeds
import services.mcc_resolver as resolver_module
from apps.transactions.models import MerchantResolution, Transactions
from services.llm_client import LLMUnavailable
from services.merchant_normalize import merchant_key
from services.upload_pipeline import UploadBudget, process_upload


# Codes the seeded catalog needs so resolve_mcc / Tier 5 can return them.
CATALOG = (
    "5411", "5812", "5814", "4789", "5999", "4111", "4121", "5942",
)


def _csv(*lines: str) -> bytes:
    header = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo"
    return ("\n".join((header, *lines)) + "\n").encode("utf-8")


class UploadBudgetTests(TestCase):
    def test_allows_while_remaining_positive(self):
        budget = UploadBudget(2)
        self.assertTrue(budget.allows())
        budget.spend()
        self.assertTrue(budget.allows())
        budget.spend()
        self.assertFalse(budget.allows())
        self.assertEqual(budget.remaining, 0)

    def test_spend_does_not_go_negative(self):
        budget = UploadBudget(0)
        budget.spend()
        self.assertEqual(budget.remaining, 0)


@override_settings(
    LLM_ENABLED=True,
    LLM_API_KEY="test-key",
    LLM_MAX_CALLS_PER_UPLOAD=2,
)
class ProcessUploadBudgetCapTests(TestCase):
    """N+1 cold merchants → llm_lookup_mcc called at most LLM_MAX_CALLS_PER_UPLOAD."""

    def setUp(self):
        resolver_module.known_mcc_codes_cache = None
        resolver_module.merchant_rules = {}
        for code in CATALOG:
            seeds.make_mcc(code=code, category="other")
        self.user_card = seeds.make_user_card()
        self.upload = seeds.make_upload(user=self.user_card.user, status="pending")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", return_value="5814")
    def test_llm_calls_capped_at_max_per_upload(self, mock_llm, mock_set, mock_get):
        # 3 distinct unknown merchants, budget=2 → exactly 2 LLM calls; the
        # third falls to Tier 5 (Food & Drink → 5812) without calling the LLM.
        file_bytes = _csv(
            "07/01/2026,07/01/2026,UNKNOWN CAFE ONE,Food & Drink,Sale,-10.00,",
            "07/01/2026,07/01/2026,UNKNOWN CAFE TWO,Food & Drink,Sale,-11.00,",
            "07/01/2026,07/01/2026,UNKNOWN CAFE THREE,Food & Drink,Sale,-12.00,",
        )

        summary = process_upload(self.upload, self.user_card, file_bytes)

        self.assertEqual(mock_llm.call_count, 2)
        self.assertEqual(summary["llm_calls"], 2)
        self.assertEqual(summary["merchants"], 3)
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(Transactions.objects.filter(upload=self.upload).count(), 3)

        # Two LLM-persisted resolutions; the third never wrote a MerchantResolution.
        self.assertEqual(MerchantResolution.objects.count(), 2)

        by_desc = {
            t.description: t.mcc_code_id
            for t in Transactions.objects.filter(upload=self.upload)
        }
        # First two got the mocked LLM answer; third got Tier 5 dining.
        llm_hits = sum(1 for mcc in by_desc.values() if mcc == "5814")
        tier5_hits = sum(1 for mcc in by_desc.values() if mcc == "5812")
        self.assertEqual(llm_hits, 2)
        self.assertEqual(tier5_hits, 1)


@override_settings(
    LLM_ENABLED=True,
    LLM_API_KEY="test-key",
    LLM_MAX_CALLS_PER_UPLOAD=25,
)
class ProcessUploadIdempotencyTests(TestCase):
    def setUp(self):
        resolver_module.known_mcc_codes_cache = None
        resolver_module.merchant_rules = {}
        for code in CATALOG:
            seeds.make_mcc(code=code, category="other")
        self.user_card = seeds.make_user_card()
        self.upload = seeds.make_upload(user=self.user_card.user, status="pending")
        self.file_bytes = _csv(
            "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,",
            "07/08/2026,07/10/2026,MTA*NYCT PAYGO,Travel,Sale,-3.00,",
            "07/08/2026,07/10/2026,MTA*NYCT PAYGO,Travel,Sale,-3.00,",
            "07/06/2026,07/06/2026,FOREIGN TRANSACTION FEE,Fees & Adjustments,Fee,-0.99,",
        )

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", side_effect=["5411", "4111", None])
    def test_second_run_updates_in_place_and_skips_llm(
        self, mock_llm, mock_set, mock_get
    ):
        first = process_upload(self.upload, self.user_card, self.file_bytes)
        self.assertEqual(first["created"], 4)
        self.assertEqual(first["updated"], 0)
        # WAL MART + MTA (+ fee burns an LLM call that returns None) = 3 calls,
        # but MTA is deduped across two rows → still 3 distinct resolution keys.
        self.assertEqual(first["merchants"], 3)
        self.assertEqual(first["llm_calls"], 3)
        self.assertEqual(mock_llm.call_count, 3)

        txs_after_first = list(
            Transactions.objects.filter(upload=self.upload)
            .order_by("row_index")
            .values_list("row_index", "description", "amount", "mcc_code_id")
        )
        self.assertEqual(Transactions.objects.filter(upload=self.upload).count(), 4)

        # Second pass: DB hits for merchants already in MerchantResolution →
        # zero LLM calls, update_or_create refreshes the same 4 rows.
        mock_llm.reset_mock()
        # Simulate Redis still cold so Tier 3b (DB) is what saves the second run.
        second = process_upload(self.upload, self.user_card, self.file_bytes)

        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 4)
        self.assertEqual(second["llm_calls"], 0)
        mock_llm.assert_not_called()

        txs_after_second = list(
            Transactions.objects.filter(upload=self.upload)
            .order_by("row_index")
            .values_list("row_index", "description", "amount", "mcc_code_id")
        )
        self.assertEqual(txs_after_first, txs_after_second)
        self.assertEqual(self.upload.status, "processed")

        # Fee row stayed uncategorized (LLM returned None → sentinel).
        fee = Transactions.objects.get(upload=self.upload, description="FOREIGN TRANSACTION FEE")
        self.assertIsNone(fee.mcc_code_id)

        walmart = Transactions.objects.get(upload=self.upload, description="WAL-MART #2297")
        self.assertEqual(walmart.amount, Decimal("35.34"))
        self.assertEqual(walmart.transaction_date, date(2026, 7, 16))
        self.assertEqual(walmart.mcc_code_id, "5411")

        # Two MTA rows share one MerchantResolution.
        self.assertEqual(
            MerchantResolution.objects.filter(
                merchant_key=merchant_key("MTA*NYCT PAYGO")
            ).count(),
            1,
        )


@override_settings(
    LLM_ENABLED=True,
    LLM_API_KEY="test-key",
    LLM_MAX_CALLS_PER_UPLOAD=25,
)
class ProcessUploadProviderOutageTests(TestCase):
    """A provider outage degrades to Tier 5 and leaves no wrong facts behind."""

    def setUp(self):
        resolver_module.known_mcc_codes_cache = None
        resolver_module.merchant_rules = {}
        for code in CATALOG:
            seeds.make_mcc(code=code, category="other")
        self.user_card = seeds.make_user_card()
        self.upload = seeds.make_upload(user=self.user_card.user, status="pending")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc", side_effect=LLMUnavailable("down"))
    def test_outage_uses_tier5_and_writes_no_resolutions(self, mock_llm, mock_set, mock_get):
        file_bytes = _csv(
            "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,",
            "07/12/2026,07/13/2026,MCDONALD'S F31398,Food & Drink,Sale,-4.66,",
        )
        summary = process_upload(self.upload, self.user_card, file_bytes)

        self.assertEqual(summary["llm_calls"], 2)  # attempts, not successes
        self.assertEqual(MerchantResolution.objects.count(), 0)
        by_desc = {
            tx.description: tx.mcc_code_id
            for tx in Transactions.objects.filter(upload=self.upload)
        }
        self.assertEqual(by_desc["WAL-MART #2297"], "5411")       # Tier 5 groceries
        self.assertEqual(by_desc["MCDONALD'S F31398"], "5812")    # Tier 5 dining


@override_settings(LLM_ENABLED=False, LLM_API_KEY="")
class ProcessUploadLlmDisabledFallsToTier5Tests(TestCase):
    def setUp(self):
        resolver_module.known_mcc_codes_cache = None
        resolver_module.merchant_rules = {}
        for code in CATALOG:
            seeds.make_mcc(code=code, category="other")
        self.user_card = seeds.make_user_card()
        self.upload = seeds.make_upload(user=self.user_card.user, status="pending")

    @patch.object(resolver_module, "cache_get", return_value=None)
    @patch.object(resolver_module, "cache_set")
    @patch("services.llm_client.llm_lookup_mcc")
    def test_disabled_llm_uses_tier5_without_persisting(self, mock_llm, mock_set, mock_get):
        file_bytes = _csv(
            "07/16/2026,07/17/2026,WAL-MART #2297,Groceries,Sale,-35.34,",
        )
        summary = process_upload(self.upload, self.user_card, file_bytes)

        mock_llm.assert_not_called()
        self.assertEqual(summary["llm_calls"], 0)
        self.assertEqual(MerchantResolution.objects.count(), 0)
        tx = Transactions.objects.get(upload=self.upload)
        self.assertEqual(tx.mcc_code_id, "5411")  # Tier 5 groceries
