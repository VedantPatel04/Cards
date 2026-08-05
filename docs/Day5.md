# Day 5 — Spend Summary Endpoint

## Checkpoint

`GET /api/summary/` returns correct per-category totals, verified by a truth-dataset test suite.

---

## Overview

Day 5 implements the aggregation layer that sits between the upload pipeline (Day 4) and the recommendation engine (Day 6). The primary deliverable is `services/spending_aggregator.py` and the `GET /api/summary/` endpoint that exposes it.

This is Stage 1 (Transaction Analysis) in `docs/Recommendation_Engine_Architecture.html`.

---

## Decisions Made

### Net spend — `Sum(amount)` per category
Refunds (negative amounts) reduce the category total. A dining refund reduces `by_category["dining"]`. Card payments land in `other` as negatives and reduce that bucket.

**Why:** Gross-only spend would overstate value, and the recommendation engine's Confidence Check (Stage 5) already flags refund distortion.

### Unresolved `""` excluded from `by_category`, reported as metadata
Rows with `category=""` are intentionally absent from spend totals. They appear as `unresolved_count` and `unresolved_amount` so the confidence check knows how much spend is uncategorised.

**Why:** Dumping unknowns into `other` poisons Day 6 scoring — this was established in Day 4 architecture.

### All 7 buckets always present
`by_category` and `annualized` always include all 7 reward categories even if zero. The Day 6 scorer iterates over all categories without guarding for missing keys.

### Negative totals are valid
`other` can be negative when card payment rows outweigh real "other" spend. This is not clamped. Stage 5 handles distortion detection.

### Scope: all-time, all wallet cards, no query filters
MVP aggregates everything the user has uploaded. Date range and per-card filters are not in scope for Day 5 or 6.

### Annualised estimates belong in the aggregator
Stage 1 of the recommendation pipeline outputs "annualized estimates." The aggregator computes them (`by_category[c] × 365 / days_span`) so Day 6 receives a stable, pre-computed value rather than re-deriving it.

---

## Response Shape

```json
{
  "period": {
    "earliest": "2025-01-15",
    "latest":   "2025-05-30",
    "days_span": 136
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
    "dining":       "2261.44",
    "groceries":     "575.10",
    "travel":          "0.00",
    "gas":             "0.00",
    "entertainment":  "134.19",
    "shopping":       "837.50",
    "other":          "121.88"
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
- `test_truth_dataset` — nets (incl. refund + negative `other`), unresolved metadata, zero-fill, period, annualised math
- `test_empty_wallet` — zeroed structure, no exceptions
- `test_user_isolation` — other user's txs never appear

**`SpendSummaryAPITest`** (2 tests): auth required (401); wire format (2-decimal strings) + HTTP user scoping.
