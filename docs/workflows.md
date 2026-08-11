# Backend workflows

Run commands from `backend/` with the venv active and `DJANGO_SETTINGS_MODULE=config.settings.local` (see [settings-architecture.md](settings-architecture.md)). API request/response shapes: [postman/Cards_API.postman_collection.json](postman/Cards_API.postman_collection.json).

---

## 1. First-time / reset local setup

```bash
cd backend
python manage.py migrate
python manage.py setup_dev
python manage.py runserver
```

`setup_dev` does, in order:

1. `seed_cards` — loads `data/card_catalog/card_catalog.json` into `Card_Products` + `Reward_Rules`
2. `seed_global_merchants` — loads `data/card_catalog/global_merchant_aliases.json` into `GlobalMerchantAlias`
3. Ensures demo user + at least one wallet card

Printed credentials (always):


| Field        | Value                                       |
| ------------ | ------------------------------------------- |
| username     | `user1`                                     |
| email        | `user1@example.com`                         |
| password     | `user1Password`                             |
| user_card_id | printed integer (use for statement uploads) |


Re-running `setup_dev` is safe: reseeds catalog/aliases, resets `user1`’s password, and **does not** duplicate a wallet card if one already exists.

Optional pieces (only if you are not using `setup_dev`):

```bash
python manage.py seed_cards
python manage.py seed_global_merchants          # upsert
python manage.py seed_global_merchants --clear  # wipe aliases table, then upsert
```

Redis (`REDIS_URL`, default `redis://localhost:6379/0`) caches user merchant answers. If Redis is down, uploads and review still work (fail-open); only override lookups skip the cache.

---



## 2. Wallet: catalog card vs custom card

Goal: prove both add paths and that catalog products stay recommendable while custom ones do not.

### 2a. Catalog card (from `card_catalog.json`)

1. Run `setup_dev` (or ensure seeds + `user1` exist).
2. Log in as `user1` (Postman: Get Token). Collection auth should inherit `{{access_token}}` — do not paste JWTs into each request.
3. List catalog products → note a `card_product_id` you do **not** already own (or delete an existing wallet entry first; hard delete also removes that card’s transactions and any statement imports left with zero rows).
4. Add to wallet with that `card_product_id`.
5. List wallet → entry shows `is_catalog: true`, and its `id` is the `user_card_id` for uploads.
6. List catalog again → same product still appears (catalog is not the wallet).

**Expect:** duplicate add of the same product → error that it already exists in the wallet. Inactive / unknown product ids → rejected.

### 2b. Custom card (not in catalog)

1. Authenticated as `user1`.
2. Add to wallet with **all three** of: `name`, `issuer`, `network` (no `card_product_id`).
3. List wallet → `is_catalog: false`, zero reward fields on the underlying product, no reward rules.
4. List catalog → custom product **must not** appear.
5. Add the same `name` + `issuer` again → rejected as already in wallet.
6. Add `name`/`issuer` that exactly match a catalog product (e.g. Freedom Unlimited / Chase) → attaches the **catalog** row (`is_catalog: true`), does not create a second product.
7. Delete the custom wallet entry → wallet row and its transactions gone; statement imports left with no transactions are removed; the orphan custom `Card_Products` row is removed. Deleting a **catalog** wallet entry does **not** delete the catalog product.

---



## 3. Statement upload pipeline (sample Chase files)

Prerequisite: authenticated `user1` and a wallet `user_card_id` (from `setup_dev` or workflow 2).

Sample files (under `backend/data/sample_uploads/`):


| File                              | Role                                          |
| --------------------------------- | --------------------------------------------- |
| `Chase Transaction Statement.csv` | Short mixed statement (good first smoke test) |
| `Chase_MAY_Transactions.csv`      | Slightly larger real-ish May export           |




### 3a. Happy path

1. Upload CSV(s) with form fields `file` (repeat the key for multiple statements) + `user_card_id`.
2. Confirm response:
  - One file → `status: processed`, `summary.rows` matches data rows, `created` / `updated` as appropriate.
  - Multiple files → `{ count, succeeded, failed, results[] }` with per-file `ok` / `summary` or `detail`.
3. List transactions → each row has `card_name` / `issuer` joined from the wallet product; `category` and `resolution_source` populated.
4. Open review queue → only merchants with `category == ""` appear. Empty queue is valid when coverage is 100%.

Re-upload **the same file bytes** with the **same** `user_card_id` → same `Uploads` row; transactions refresh by `(upload, row_index)`.

Same bytes with a **different** `user_card_id` → **409 Conflict** (no silent card move). To fix a wrong-card import **without re-uploading**:

1. `GET /api/uploads/` → pick the row by `filename` (e.g. `Chase_MAY_Transactions.csv`) and note its `upload_id`
2. Optionally confirm on `GET /api/transactions/` — each row now includes `upload_id` + `filename`
3. `POST /api/uploads/<upload_id>/reassign/` with `{ "user_card_id": <destination wallet id> }`
4. Every transaction on that statement moves to the new card (upload-level only; no audit trail yet)

To remove a statement entirely: `DELETE /api/uploads/<upload_id>/` → **204**; that import's transactions cascade away (summary / recommendations update on next read).

### 3b. What to expect for `Chase_MAY_Transactions.csv`

About 15 data rows. With globals seeded, expect **high / full coverage** (`needs_review` near 0):

- Global hits (examples): `TARGET` → shopping; `TACO BELL`, `CHIPOTLE` → dining  
- Bank-mapped hits: Chase `Travel` / `Food & Drink` / `Shopping` → travel / dining / shopping  
- Forced or mapped `other`: bills/utilities-style rows, professional services, card payment thank-you

Normalization quirks (not failures): e.g. `AMTRAK .COM…` may key as `AMTRAK COM` and resolve via **bank** travel even if the alias table has `AMTRAK`; long location strings (e.g. In-N-Out + city) may miss a short global key and still resolve via Chase’s category.

### 3c. Review loop (when something is unresolved)

Only needed if upload `needs_review` > 0 or review queue is non-empty.

1. List review queue → pick a `merchant_key` (highest spend first).
2. Submit an answer with that key + a rewards category (`dining`  `groceries`  `travel`  `gas`  `entertainment`  `shopping`  `other`).
3. List review again → that merchant gone.
4. List transactions → those rows show the chosen category; `resolution_source` reflects user authority after backfill.
5. Upload another statement containing the same merchant → should resolve from the user override (Redis cache and/or `MerchantResolution`), not reappear in review.

---



## 4. Refresh global aliases after editing JSON

If you change `data/card_catalog/global_merchant_aliases.json`:

```bash
python manage.py seed_global_merchants
```

Then re-upload a statement (or rely on new uploads) to see new global hits. The resolver keeps an in-process alias map; `seed_global_merchants` invalidates it. Restart `runserver` if a long-lived process still looks stale.

Do **not** put raw Chase description strings in `merchant_key` — keys must match `merchant_key()` output (uppercase, normalized).

---



## 5. Automated tests (critical suites)

```bash
cd backend
python manage.py test tests.test_wallet tests.test_review tests.test_summary tests.services.test_category_resolver tests.services.test_upload_pipeline tests.services.test_merchant_normalize tests.services.test_csv_parser
```

Uses `config.settings.test` via the test runner. These suites cover wallet catalog/custom behavior, review isolation, spend summary (service + HTTP layer), resolver tiers (including dead Redis), upload pipeline, and Chase CSV parsing.

---



## 6. Spend summary

Prerequisite: authenticated user with at least one upload (workflow 3).

```
GET /api/summary/
```

Returns all-time spend totals by rewards category across all wallet cards.

**Key fields:**


| Field                                    | Notes                                                                               |
| ---------------------------------------- | ----------------------------------------------------------------------------------- |
| `by_category`                            | All 7 buckets always present; net spend (refunds reduce totals)                     |
| `annualized`                             | Projected annual spend per category (`by_category × 12 / months_covered`)           |
| `period.months_covered`                  | Statement-cycle evidence: sum over uploads of `max(1, round(span_days/30))`         |
| `period.months_breakdown`                | Calendar-month histogram (display only; may list more months than `months_covered`) |
| `total_spend`                            | Sum of purchase/refund `by_category` values (payments/adjustments excluded)         |
| `categorized_pct`                        | Count-based coverage; improves as you clear the review queue                        |
| `unresolved_count` / `unresolved_amount` | Rows still needing review                                                           |
| `period`                                 | `earliest`, `latest` transaction date and `days_span`                               |


**Normal flow:**

1. Upload a statement (workflow 3).
2. Clear the review queue to maximise `categorized_pct` (workflow 3c).
3. `GET /api/summary/` → confirm `by_category` totals are plausible for the uploaded data.

**What to watch for:**

- Bill payments and statement adjustments are excluded from spend totals (`entry_type` payment/adjustment). Refunds still reduce the matching category.
- `categorized_pct < 100` means unresolved rows are excluded from `by_category`; answer review items to close the gap.
- `days_span` is display only. Do not extrapolate from it when uploads have gaps.
- `months_covered` is the extrapolation base (statement cycles). `months_breakdown` can show more calendar months than `months_covered` when a cycle spills across month labels — that is expected.
- Day 6 recommendations call this service internally; keeping coverage high produces more accurate recommendations.

---



## 7. Card recommendations

Prerequisite: authenticated user. Meaningful ranks need uploaded spend (workflow 3) and preferably a cleared review queue (workflow 3c / summary coverage).

```
GET /api/recommendations/
```

Returns up to 5 catalog cards scored against this user's all-time spend summary. **Every money field is estimated US dollars per year** — the envelope's `value_basis` states the currency, the months of data behind it, and what a point is assumed to be worth.

**Key fields:**


| Field                            | Notes                                                                                   |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| `confidence` / `confidence_note` | From summary quality (sparse / coverage / distortion)                                   |
| `value_basis`                    | `currency`, `months_of_data`, `point_value_cents` — the assumptions behind every number |
| `recommendations[].rank`         | Competition rank; ties share a rank (e.g. 1, 1, 3)                                      |
| `recommendations[].rank_note`    | **Omitted entirely** unless this card ties with peers                                   |
| `headline`                       | One plain sentence: what the card is worth, or why the fee makes it a loss              |
| `spending_score`                 | Annual reward value: annualized spend × effective rate (negatives floored)              |
| `signup_bonus_*`                 | Status `met` / `not_met` / `insufficient_data` / `no_bonus`                             |
| `total_score`                    | First year: `spending_score − annual_fee + signup_bonus_score`                          |
| `ongoing_annual_value`           | Every year after: `spending_score − annual_fee` (no bonus)                              |
| `break_even_annual_spend`        | Spend at this user's mix that would cover the fee; `null` when there is no fee          |
| `reward_currency`                | `cash_back`, `points` or `miles`; points are converted before comparison                |
| `explanation`                    | Per-category published rate, effective rate, annualized spend, value                    |


**Normal flow:**

1. Upload statements + clear review (workflows 3 / 3c).
2. Optional: `GET /api/summary/` to sanity-check `months_covered` and `categorized_pct`.
3. `GET /api/recommendations/` → inspect ranks, bonus statuses, and confidence.

**What to watch for:**

- Length may be 0–5; do not assume exactly 5.
- **Negative totals are a feature.** They mean the annual fee costs more than the card returns; `headline` and `break_even_annual_spend` say by how much and what it would take to flip.
- Signup bonus: if purchase spend already clears the required amount → `met` even with fewer statement-months than the card's window (early finish is allowed). If still under the bar and `months_covered` is short of the window → `insufficient_data` and the note says how many more months to upload.
- Empty wallet still returns 200 with low confidence.
- `by_category` (actual) drives bonus projection; `annualized` drives spending score — they are not interchangeable.
- A card's issuer wording (`us_supermarkets`) is folded onto the 7 buckets by `reward_rule_aliases.json`. Adding a card with an unlisted label fails ingestion on purpose — map it there first, to a bucket or to `null`.

---



## 8. Automated end-to-end run

Everything in workflows 1–7 as one command. Use it to smoke the stack after a change instead of clicking through Postman.

```bash
cd backend && python manage.py runserver   # terminal 1
./scripts/demo_flow.sh                     # terminal 2, from the repo root
```

The script seeds (`setup_dev`), registers/logs in, resolves a wallet card, uploads both sample statements, clears the review queue, then asserts the Day 6 contract on `GET /api/recommendations/`: field set, 2-decimal money strings, `total_score = spending_score − annual_fee + signup_bonus_score` (±1¢ for independent rounding), valid bonus statuses, competition ranks, and a 401 without a token. It prints the ranked table plus the winner's per-category explanation and exits non-zero if any check fails.


| Flag / env              | Effect                                                       |
| ----------------------- | ------------------------------------------------------------ |
| `--no-setup`            | Skip `setup_dev` (keep the DB exactly as-is)                 |
| `BASE_URL=…`            | Point at another host/port (default `http://127.0.0.1:8000`) |
| `USERNAME` / `PASSWORD` | Run as someone other than `user1`                            |


Re-runnable: a re-uploaded statement returns `200` (refresh), and a statement already bound to a **different** wallet card returns `409` — the script then calls reassign rather than re-uploading, matching workflow 3d.

Requires `curl` + `jq`.

### Headless Postman (same assertions, no GUI)

Request 12 carries the contract assertions as a Postman test script, so the collection can run itself:

```bash
npx newman run docs/postman/Cards_API.postman_collection.json \
  --folder "2. Get Token (login)" --folder "12. Recommendations (protected)"
```

Run `demo_flow.sh` (or the upload steps in the GUI) first so there is spend to score.

---



## Quick checklist


| Goal                    | Command / action                                                      |
| ----------------------- | --------------------------------------------------------------------- |
| Boot demo environment   | `migrate` → `setup_dev` → `runserver`                                 |
| Catalog wallet card     | Add by `card_product_id`; confirm `is_catalog: true`                  |
| Custom wallet card      | Add `name` + `issuer` + `network`; confirm absent from catalog list   |
| Smoke a statement       | Upload a file under `data/sample_uploads/` with a real `user_card_id` |
| Prove user override     | Answer review → re-upload same merchant → stays categorized           |
| Update merchant globals | Edit aliases JSON → `seed_global_merchants`                           |
| Spend summary           | `GET /api/summary/` after uploading a statement                       |
| Card recommendations    | `GET /api/recommendations/` after summary looks sane                  |
| Whole flow, automated   | `./scripts/demo_flow.sh` against a running server                     |
| API shapes              | Postman collection only                                               |


