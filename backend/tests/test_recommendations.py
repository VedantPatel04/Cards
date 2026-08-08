from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import seeds
from apps.cards.models import Card_Products, Reward_Rules
from services.card_catalog_ingestion import ingest_card_catalog
from services.category_resolver import reward_categories
from services.recommendation_engine import (
    ZERO,
    _card_passes_gate,
    compute_confidence,
    fold_rules_to_buckets,
    get_valid_cards,
    score_card,
    select_top_cards,
)

ALL_CATEGORIES = sorted(reward_categories())


def _ann(**overrides) -> dict:
    base = {c: ZERO for c in ALL_CATEGORIES}
    base.update(overrides)
    return base


def _by(**overrides) -> dict:
    return _ann(**overrides)


def _catalog_card(name, issuer):
    return Card_Products.objects.prefetch_related("reward_rules").get(
        name=name, issuer=issuer
    )


class RecommendationEngineTest(TestCase):
    def setUp(self):
        ingest_card_catalog()
        self.freedom = _catalog_card("Freedom Unlimited", "Chase")
        self.sapphire = _catalog_card("Sapphire Preferred", "Chase")
        self.active = _catalog_card("Active Cash", "Wells Fargo")

    def test_ranking_on_spend_prefers_higher_category_earn(self):
        annualized = _ann(dining=Decimal("10000.00"))
        by_category = _by(dining=Decimal("100.00"))
        scored = [
            score_card(c, annualized, by_category, 1)
            for c in (self.sapphire, self.active)
        ]
        top = select_top_cards(scored, annualized, limit=2)
        self.assertEqual(top[0]["card"].name, "Sapphire Preferred")
        self.assertGreater(top[0]["spending_score"], top[1]["spending_score"])

    def test_annual_fee_deduction_breaks_equal_spend(self):
        annualized = _ann(dining=Decimal("1000.00"))
        by_category = _by()
        a = score_card(self.freedom, annualized, by_category, months_covered=1)
        b = score_card(self.sapphire, annualized, by_category, months_covered=1)
        a["spending_score"] = Decimal("50.00")
        b["spending_score"] = Decimal("50.00")
        a["total_score"] = a["spending_score"] - a["card"].annual_fee + a["signup_bonus_score"]
        b["total_score"] = b["spending_score"] - b["card"].annual_fee + b["signup_bonus_score"]
        top = select_top_cards([a, b], annualized, limit=2)
        self.assertEqual(top[0]["card"].name, "Freedom Unlimited")
        self.assertEqual(top[1]["card"].name, "Sapphire Preferred")

    def test_gate_excludes_zero_rate_rule(self):
        card = seeds.make_card(
            name="Bad Rate Card",
            issuer="TestBank",
            is_catalog=True,
            base_reward_rate=Decimal("1.00"),
        )
        seeds.make_reward_rule(card=card, category="dining", reward_rate=Decimal("0.00"))
        names = {c.name for c in get_valid_cards()}
        self.assertNotIn("Bad Rate Card", names)

    def test_active_cash_passes_gate(self):
        known = reward_categories()
        self.assertTrue(_card_passes_gate(self.active, known))
        self.assertIn(self.active, get_valid_cards())


class RuleFoldingTest(TestCase):
    """Issuer wording collapses onto the seven buckets transactions can produce."""

    def setUp(self):
        ingest_card_catalog()

    def test_multiple_travel_rules_fold_to_the_lowest_rate(self):
        # Sapphire pays 5% via the Chase portal, 3% on vacation rentals and 2%
        # on everything else that is travel. Only the 2% is unconditional.
        folded = fold_rules_to_buckets(_catalog_card("Sapphire Preferred", "Chase"))
        self.assertEqual(folded["travel"], Decimal("2.00"))

    def test_issuer_wording_maps_onto_buckets(self):
        folded = fold_rules_to_buckets(_catalog_card("Blue Cash Preferred", "American Express"))
        self.assertEqual(folded["groceries"], Decimal("6.00"))
        self.assertEqual(folded["entertainment"], Decimal("6.00"))
        self.assertEqual(folded["travel"], Decimal("3.00"))
    def test_unscored_rule_is_ignored_and_falls_back_to_base_rate(self):
        # Discover's only rule is a rotating, activation-gated category mapped
        # to null, so travel spend earns the 1% base rate rather than 5%.
        discover = _catalog_card("Discover it Cash Back", "Discover")
        self.assertEqual(fold_rules_to_buckets(discover), {})
        r = score_card(discover, _ann(travel=Decimal("1000.00")), _by(), 1)
        self.assertEqual(r["spending_score"], Decimal("10.00"))


class RewardCurrencyTest(TestCase):
    """Points and miles are counts; they must become dollars before comparison."""

    def setUp(self):
        ingest_card_catalog()
        self.sapphire = _catalog_card("Sapphire Preferred", "Chase")

    def test_points_bonus_converts_to_dollars(self):
        self.assertEqual(self.sapphire.reward_currency, "points")
        r = score_card(
            self.sapphire,
            _ann(),
            _by(dining=Decimal("5000.00")),
            months_covered=3,
        )
        self.assertEqual(r["signup_bonus_status"], "met")
        # 75,000 points at the default 1.0 cents each
        self.assertEqual(r["signup_bonus_score"], Decimal("750.00"))

    def test_cash_back_bonus_is_taken_at_face_value(self):
        freedom = _catalog_card("Freedom Unlimited", "Chase")
        r = score_card(freedom, _ann(), _by(dining=Decimal("500.00")), months_covered=3)
        self.assertEqual(r["signup_bonus_status"], "met")
        self.assertEqual(r["signup_bonus_score"], freedom.signup_bonus)

    def test_points_earn_rate_converts_at_the_same_valuation(self):
        # 3 points per dollar on dining, valued at 1 cent, is 3% of spend.
        r = score_card(self.sapphire, _ann(dining=Decimal("1000.00")), _by(), 1)
        dining = next(e for e in r["explanation"] if e["category"] == "dining")
        self.assertEqual(dining["rate"], "3.00")
        self.assertEqual(dining["effective_rate"], "3.00")
        self.assertEqual(dining["value"], "30.00")


class SignupBonusTest(TestCase):
    def setUp(self):
        ingest_card_catalog()
        self.freedom = _catalog_card("Freedom Unlimited", "Chase")

    def test_insufficient_data_counts_whole_months_still_needed(self):
        r = score_card(self.freedom, _ann(), _by(dining=Decimal("5000.00")), months_covered=1)
        self.assertEqual(r["signup_bonus_status"], "insufficient_data")
        self.assertEqual(r["signup_bonus_score"], ZERO)
        self.assertIn("Upload 2 more month(s)", r["signup_bonus_note"])
        d = r["signup_bonus_detail"]
        self.assertEqual(d["status"], "insufficient_data")
        self.assertEqual(d["months_of_data"], 1)
        self.assertEqual(d["months_needed"], 2)
        self.assertEqual(d["period_months"], 3)
        self.assertIn("required_spend", d)

    def test_no_data_at_all_is_insufficient_not_a_crash(self):
        r = score_card(self.freedom, _ann(), _by(), months_covered=0)
        self.assertEqual(r["signup_bonus_status"], "insufficient_data")
        self.assertIn("Upload 3 more month(s)", r["signup_bonus_note"])
        self.assertEqual(r["signup_bonus_detail"]["months_of_data"], 0)

    def test_not_met(self):
        r = score_card(self.freedom, _ann(), _by(dining=Decimal("100.00")), months_covered=3)
        self.assertEqual(r["signup_bonus_status"], "not_met")
        self.assertEqual(r["signup_bonus_score"], ZERO)
        self.assertIn("short of", r["signup_bonus_note"])
        d = r["signup_bonus_detail"]
        self.assertEqual(d["status"], "not_met")
        self.assertEqual(d["positive_actual_spend"], "100.00")
        self.assertEqual(d["monthly_average"], "33.33")
        self.assertEqual(d["projected_spend"], "100.00")  # 33.33 × 3
        self.assertEqual(d["required_spend"], "500.00")
        self.assertEqual(d["period_months"], 3)
        self.assertEqual(d["months_of_data"], 3)

    def test_no_bonus_skips_period_check(self):
        card = seeds.make_card(
            name="No Bonus Card",
            issuer="TestBank",
            is_catalog=True,
            signup_bonus=ZERO,
            signup_bonus_required_spending=ZERO,
            base_reward_rate=Decimal("2.00"),
        )
        r = score_card(card, _ann(), _by(dining=Decimal("999.00")), months_covered=0)
        self.assertEqual(r["signup_bonus_status"], "no_bonus")
        self.assertEqual(r["signup_bonus_note"], "")
        self.assertEqual(r["signup_bonus_score"], ZERO)
        self.assertEqual(r["signup_bonus_detail"], {"status": "no_bonus"})

    def test_statements_with_a_gap_are_counted_as_months_not_calendar_days(self):
        r = score_card(self.freedom, _ann(), _by(dining=Decimal("409.08")), months_covered=2)
        self.assertEqual(r["signup_bonus_status"], "insufficient_data")
        self.assertIn("Upload 1 more month(s)", r["signup_bonus_note"])

    def test_projection_scales_by_months_of_evidence(self):
        # 300 across 3 months projects to 300 — short of the 500 required.
        r = score_card(self.freedom, _ann(), _by(dining=Decimal("300.00")), months_covered=3)
        self.assertEqual(r["signup_bonus_status"], "not_met")
        self.assertIn("$300.00", r["signup_bonus_note"])


class CardValueFramingTest(TestCase):
    def setUp(self):
        ingest_card_catalog()

    def test_fee_card_reports_negative_ongoing_value_and_break_even(self):
        blue = _catalog_card("Blue Cash Preferred", "American Express")
        r = score_card(blue, _ann(groceries=Decimal("1000.00")), _by(), months_covered=1)
        # 6% of 1000 = 60, against a 95 fee
        self.assertEqual(r["spending_score"], Decimal("60.00"))
        self.assertEqual(r["ongoing_annual_value"], Decimal("-35.00"))
        # 95 / (60/1000) = 1583.33 of spend at this mix to cover the fee
        self.assertAlmostEqual(
            r["break_even_annual_spend"], Decimal("1583.3333"), places=3
        )

    def test_no_fee_card_has_no_break_even(self):
        active = _catalog_card("Active Cash", "Wells Fargo")
        r = score_card(active, _ann(dining=Decimal("1000.00")), _by(), months_covered=1)
        self.assertIsNone(r["break_even_annual_spend"])
        self.assertEqual(r["ongoing_annual_value"], r["spending_score"])

    def test_ongoing_value_excludes_the_one_time_bonus(self):
        freedom = _catalog_card("Freedom Unlimited", "Chase")
        r = score_card(
            freedom, _ann(dining=Decimal("1000.00")), _by(dining=Decimal("500.00")), 3
        )
        self.assertEqual(r["signup_bonus_status"], "met")
        self.assertEqual(r["total_score"], r["ongoing_annual_value"] + Decimal("200.00"))


class ScoringEdgeCaseTest(TestCase):
    def setUp(self):
        ingest_card_catalog()
        self.freedom = _catalog_card("Freedom Unlimited", "Chase")
        self.active = _catalog_card("Active Cash", "Wells Fargo")

    def test_negative_annualized_floored(self):
        r = score_card(
            self.freedom,
            _ann(other=Decimal("-100.00"), dining=Decimal("100.00")),
            _by(),
            months_covered=3,
        )
        other_row = next(e for e in r["explanation"] if e["category"] == "other")
        self.assertEqual(other_row["annualized_spend"], "0.00")
        self.assertEqual(other_row["value"], "0.00")

    def test_confidence_sparse(self):
        summary = {
            "transaction_count": 3,
            "categorized_pct": Decimal("100.0"),
            "annualized": _ann(),
        }
        level, note = compute_confidence(summary)
        self.assertEqual(level, "low")
        self.assertIn("Too few", note)

    def test_confidence_low_coverage(self):
        summary = {
            "transaction_count": 20,
            "categorized_pct": Decimal("60.0"),
            "annualized": _ann(),
        }
        level, _ = compute_confidence(summary)
        self.assertEqual(level, "low")

    def test_shared_rank_on_exhausted_tiebreak(self):
        annualized = _ann(dining=Decimal("10.00"))
        Reward_Rules.objects.filter(card_product=self.freedom).delete()
        a = score_card(_catalog_card("Freedom Unlimited", "Chase"), annualized, _by(), 1)
        b = score_card(_catalog_card("Active Cash", "Wells Fargo"), annualized, _by(), 1)
        for s in (a, b):
            s["spending_score"] = Decimal("10.00")
            s["signup_bonus_score"] = ZERO
            s["total_score"] = Decimal("10.00")
            s["card"].annual_fee = ZERO

        top = select_top_cards([a, b], annualized, limit=2)
        self.assertEqual(top[0]["rank"], 1)
        self.assertEqual(top[1]["rank"], 1)
        self.assertIn("Tied with", top[0]["rank_note"])
        self.assertIn("Tied with", top[1]["rank_note"])

    def test_fewer_cards_than_the_limit(self):
        Card_Products.objects.filter(is_catalog=True).exclude(pk=self.active.pk).update(
            is_active=False
        )
        valid = get_valid_cards()
        self.assertEqual(len(valid), 1)
        scored = [score_card(c, _ann(), _by(), 1) for c in valid]
        top = select_top_cards(scored, _ann(), limit=5)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["rank"], 1)


class RecommendationsAPITest(APITestCase):
    def setUp(self):
        ingest_card_catalog()
        self.url = reverse("recommendations")
        self.user = seeds.make_user()
        self.client.force_authenticate(user=self.user)

    def test_auth_required(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wire_shape_empty_wallet(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("confidence", resp.data)
        self.assertIn("confidence_note", resp.data)
        self.assertIn("value_basis", resp.data)
        self.assertIn("recommendations", resp.data)
        self.assertLessEqual(len(resp.data["recommendations"]), 5)
        self.assertEqual(resp.data["confidence"], "low")

        if not resp.data["recommendations"]:
            return

        rec = resp.data["recommendations"][0]
        for key in (
            "rank", "card_id", "card_name", "issuer", "reward_currency", "headline",
            "annual_fee", "spending_score", "signup_bonus_score", "signup_bonus_status",
            "signup_bonus_note", "signup_bonus_detail", "total_score", "ongoing_annual_value",
            "break_even_annual_spend", "explanation",
        ):
            self.assertIn(key, rec)
        self.assertIsInstance(rec["signup_bonus_detail"], dict)
        self.assertIn("status", rec["signup_bonus_detail"])
        self.assertIsInstance(rec["annual_fee"], str)
        self.assertIsInstance(rec["spending_score"], str)
        self.assertIsInstance(rec["total_score"], str)
        self.assertIsInstance(rec["explanation"], list)

    def test_rank_note_only_present_on_ties(self):
        resp = self.client.get(self.url)
        for rec in resp.data["recommendations"]:
            if "rank_note" in rec:
                self.assertIn("Tied with", rec["rank_note"])

    def test_returns_at_most_five_even_with_a_larger_catalog(self):
        self.assertGreater(Card_Products.objects.filter(is_catalog=True).count(), 5)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.data["recommendations"]), 5)
        ranks = [r["rank"] for r in resp.data["recommendations"]]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(ranks[0], 1)

    def test_user_scoping(self):
        baseline = self.client.get(self.url).data
        shared = Card_Products.objects.get(name="Freedom Unlimited", issuer="Chase")
        other = seeds.make_user_card(card=shared)
        seeds.make_transaction(
            upload=seeds.make_upload(user=other.user),
            user_card=other,
            category="dining",
            amount=Decimal("9999.00"),
            row_index=0,
        )
        after = self.client.get(self.url).data
        self.assertEqual(baseline["confidence"], after["confidence"])
        self.assertEqual(
            [r["card_id"] for r in baseline["recommendations"]],
            [r["card_id"] for r in after["recommendations"]],
        )
        self.assertEqual(
            [r["total_score"] for r in baseline["recommendations"]],
            [r["total_score"] for r in after["recommendations"]],
        )

    def test_response_handles_fewer_than_the_limit(self):
        Card_Products.objects.filter(is_catalog=True).update(is_active=False)
        Card_Products.objects.filter(name="Active Cash").update(is_active=True)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(resp.data["recommendations"]), 1)
