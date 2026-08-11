# Day 5 — Spend Summary Endpoint

## Checkpoint

`GET /api/summary/` returns correct per-category totals, verified by a truth-dataset test suite.

---

## Overview

Day 5 implements the aggregation layer that sits between the upload pipeline (Day 4) and the recommendation engine (Day 6). The primary deliverable is `services/spending_aggregator.py` and the `GET /api/summary/` endpoint that exposes it.

This is Stage 1 (Transaction Analysis) in `docs/Recommendation_Engine_Architecture.html`.

---

## Decisions Made

### Spend totals — purchases and refunds only
`by_category` / `total_spend` sum rows with `entry_type` of `spend` or `refund`. Refunds (negative amounts) reduce the matching category. A dining refund reduces `by_category["dining"]`.

**Bill payments** (`entry_type=payment`) and **statement adjustments** (`entry_type=adjustment`) stay on the transaction ledger but are **excluded** from spend totals. Paying your credit card bill is not purchase spend for signup-bonus or rewards math.

**Why (revised):** The earlier rule that let payments land in `other` as negatives understated true purchase spend (e.g. ~$655 purchases − ~$384 payments → ~$271). Issuers award bonuses on purchases, not on net-of-payments.

Chase `Type` is mapped in `csv_parser` (`Sale`/`Fee` → spend, `Return` → refund, `Payment` → payment, `Adjustment` → adjustment). Existing DB rows with description containing `Payment Thank You` are backfilled to `payment` on migrate; other legacy credits need a re-upload to pick up `Type`.

### Unresolved `""` excluded from `by_category`, reported as metadata
Rows with `category=""` are intentionally absent from spend totals. They appear as `unresolved_count` and `unresolved_amount` so the confidence check knows how much spend is uncategorised.

**Why:** Dumping unknowns into `other` poisons Day 6 scoring — this was established in Day 4 architecture.

### All 7 buckets always present
`by_category` and `annualized` always include all 7 reward categories even if zero. The Day 6 scorer iterates over all categories without guarding for missing keys.

### Period includes the full ledger
`transaction_count` and `months_breakdown` include payments/adjustments. `months_covered` is statement-cycle evidence (per-upload ~30-day spans); a payment-only upload still contributes at least 1 via `max(1, …)`.

### Scope: all-time, all wallet cards, no query filters
MVP aggregates everything the user has uploaded. Date range and per-card filters are not in scope for Day 5 or 6.

### Annualised estimates belong in the aggregator
Stage 1 of the recommendation pipeline outputs "annualized estimates." The aggregator computes them so Day 6 receives a stable, pre-computed value rather than re-deriving it.

```
annualized[c] = by_category[c] × 12 / months_covered
```

### Coverage is counted in statement cycles, not calendar months *(revised)*
`months_covered` sums, per upload, `max(1, round(inclusive_span_days / 30))`. That matches ~30-day billing statements: a mid-month cycle that lands in two calendar months still counts as **one** month of evidence. Two statement files that spill across three calendar labels still count as **two**.

`months_breakdown` stays a **calendar-month** histogram for display/debugging and is intentionally separate from `months_covered`.

`days_span` is still reported, but **must not** be used to extrapolate (gaps between uploads would look like zero-spend months).

**Why:** counting distinct calendar months of `transaction_date` invented extra months from statement spillover (e.g. Jan+Feb files → Dec/Jan/Feb = 3). Signup and annualization then understated monthly averages.

**Day 6 usage note:** spending score uses `annualized`; signup-bonus projection uses actual `by_category` (not annualized) scaled by `months_covered`. See `docs/Day6-7.md`.

---

## Response Shape

```json
{
  "period": {
    "earliest": "2025-01-15",
    "latest":   "2025-05-30",
    "days_span": 136,
    "months_covered": 5
  },
  "by_category": {
    "dining":        "842.50",
    "groceries":     "214.30",
    "travel":          "0.00",
    "gas":             "0.00",
    "entertainment":  "50.00",
    "shopping":       "312.00",
    "other":           "45.40"
  },
  "annualized": {
    "dining":       "2022.00",
    "groceries":     "514.32",
    "travel":          "0.00",
    "gas":             "0.00",
    "entertainment":  "120.00",
    "shopping":       "748.80",
    "other":          "108.96"
  },
  "total_spend":      "1464.20",
  "transaction_count": 45,
  "unresolved_count":   3,
  "unresolved_amount": "67.50",
  "categorized_pct":  "93.3"
}
```

**Contracts:**
- All money values are strings, 2 decimal places (`_money` serialisation)
- `categorized_pct` is a string, 1 decimal place (count-based, matches upload pipeline convention)
- `period.earliest` / `period.latest` are ISO date strings or `null`
- Negative values (e.g. `other: "-25.00"`) are valid; Day 6 must handle them

---

## Files Changed

| File | Change |
|------|--------|
| `backend/services/spending_aggregator.py` | Implemented (was empty stub) |
| `backend/apps/transactions/views.py` | Added `summary_view` + import |
| `backend/config/urls.py` | Added `GET /api/summary/` route (`name='spend_summary'`) |
| `backend/tests/test_summary.py` | New — 5 focused tests, 2 classes |
| `docs/postman/Cards_API.postman_collection.json` | Added item 11 (Spend Summary) |
| `docs/workflows.md` | Added section 6 + quick checklist row |

---

## Day 6 Contract

`recommendation_engine.py` calls `get_spend_summary(user)` directly. It receives:

| Field | Used for |
|-------|----------|
| `by_category` | Score each card's reward rules against spend |
| `annualized` | Annual value estimate: `annualized[cat] × rule.reward_rate` |
| `categorized_pct` | Stage 5 Confidence Check — low coverage → lower confidence |
| `unresolved_count` | Stage 5 — count of items that could shift scores if resolved |
| `total_spend` | Other / uncategorised % ratio |

No changes to `spending_aggregator.py` needed for Day 6 unless scoring reveals a gap.

---

## Test Suite

Run:
```bash
cd backend
python manage.py test tests.test_summary --verbosity=2
```

**`SpendSummaryServiceTest`** (3 tests):
- `test_truth_dataset` — nets (refund reduces dining; payment excluded), unresolved metadata, zero-fill, period, annualised math
- `test_empty_wallet` — zeroed structure, no exceptions
- `test_user_isolation` — other user's txs never appear

**`SpendSummaryAPITest`** (2 tests): auth required (401); wire format (2-decimal strings) + HTTP user scoping.
