# Dev & test workflows

Operational truth for running and verifying the backend. **Not** an API reference — request/response shapes live in [`postman/Cards_API.postman_collection.json`](postman/Cards_API.postman_collection.json).

Unless noted, run commands from `backend/` with the project venv active and `DJANGO_SETTINGS_MODULE=config.settings.local` (see [`settings-architecture.md`](settings-architecture.md)).

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

| Field | Value |
|-------|--------|
| username | `user1` |
| email | `user1@example.com` |
| password | `user1Password` |
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
3. List catalog products → note a `card_product_id` you do **not** already own (or delete an existing wallet entry first; hard delete also removes that card’s transactions).
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
7. Delete the custom wallet entry → wallet row and its transactions gone; the orphan custom `Card_Products` row is removed. Deleting a **catalog** wallet entry does **not** delete the catalog product.

---

## 3. Statement upload pipeline (sample Chase files)

Prerequisite: authenticated `user1` and a wallet `user_card_id` (from `setup_dev` or workflow 2).

Sample files (under `backend/data/sample_uploads/`):

| File | Role |
|------|------|
| `Chase Transaction Statement.csv` | Short mixed statement (good first smoke test) |
| `Chase_MAY_Transactions.csv` | Slightly larger real-ish May export |

### 3a. Happy path

1. Upload the CSV with form fields `file` + `user_card_id`.
2. Confirm response: `status: processed`, `summary.rows` matches file line count (data rows), `created` / `updated` as appropriate.
3. List transactions → each row has `card_name` / `issuer` joined from the wallet product; `category` and `resolution_source` populated.
4. Open review queue → only merchants with `category == ""` appear. Empty queue is valid when coverage is 100%.

Re-upload **the same file bytes** → same `Uploads` row (hash idempotency); transactions refresh by `(upload, row_index)` rather than duplicating.

### 3b. What to expect for `Chase_MAY_Transactions.csv`

About 15 data rows. With globals seeded, expect **high / full coverage** (`needs_review` near 0):

- Global hits (examples): `TARGET` → shopping; `TACO BELL`, `CHIPOTLE` → dining  
- Bank-mapped hits: Chase `Travel` / `Food & Drink` / `Shopping` → travel / dining / shopping  
- Forced or mapped `other`: bills/utilities-style rows, professional services, card payment thank-you  

Normalization quirks (not failures): e.g. `AMTRAK .COM…` may key as `AMTRAK COM` and resolve via **bank** travel even if the alias table has `AMTRAK`; long location strings (e.g. In-N-Out + city) may miss a short global key and still resolve via Chase’s category.

### 3c. Review loop (when something is unresolved)

Only needed if upload `needs_review` > 0 or review queue is non-empty.

1. List review queue → pick a `merchant_key` (highest spend first).
2. Submit an answer with that key + a rewards category (`dining` \| `groceries` \| `travel` \| `gas` \| `entertainment` \| `shopping` \| `other`).
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
python manage.py test tests.test_wallet tests.test_review tests.services.test_category_resolver tests.services.test_upload_pipeline tests.services.test_merchant_normalize tests.services.test_csv_parser
```

Uses `config.settings.test` via the test runner. These suites cover wallet catalog/custom behavior, review isolation, resolver tiers (including dead Redis), upload pipeline, and Chase CSV parsing.

---

## Quick checklist

| Goal | Command / action |
|------|------------------|
| Boot demo environment | `migrate` → `setup_dev` → `runserver` |
| Catalog wallet card | Add by `card_product_id`; confirm `is_catalog: true` |
| Custom wallet card | Add `name` + `issuer` + `network`; confirm absent from catalog list |
| Smoke a statement | Upload a file under `data/sample_uploads/` with a real `user_card_id` |
| Prove user override | Answer review → re-upload same merchant → stays categorized |
| Update merchant globals | Edit aliases JSON → `seed_global_merchants` |
| API shapes | Postman collection only |
