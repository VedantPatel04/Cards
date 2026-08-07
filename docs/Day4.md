# **CONTEXT OF THE PROBLEM**

API pricing - A huge blocker that eventually led to the complete restructuring of our category resolution architecture.

API's aren't cheap and running even just a tens or hundreds of calls over thousands of transactions becomes expensive if you're limited to the free tiers like I am (assuming the free tier hands out that much usage to begin with). 

### What's the real issue here?

```
I need a way to resolve merchant categories without making calls to any API, whether that be for an LLM or VISA developers or PLAID  ... you get the point.
```



### Solution

```
A new architecture that relies on a couple of things:

- A global preseeded dataset from data gathered through official merchant category code lists and other mappings published by networks and issuers like VISA, MasterfCard, Chase, etc.

- Category supplied by bank transaction statements

- User supplied data for any unresolved categories or categories which were mislabelled.

```

## **OVERVIEW OF CHANGES MADE**

---

Dropped the MCC + LLM path entirely. Categories now resolve directly to the shared rewards vocabulary (`dining` | `groceries` | `travel` | `gas` | `entertainment` | `shopping` | `other`).


## How is this done?
- By the normalization service: (`normalize_csv`). `normalize_csv` maps bank columns to category rows.
- `merchant_key()` collapses noisy transaction descriptions like store codes, `*`, `#`, `.COM`/ other web junk into practical-use lookup keys.
- Upload pipeline upserts transactions without duplication on `(upload, row_index)` with a % coverage / needs-review summary.

### ***Models (what changed / what stayed):***
- **Removed:** `MCC_Codes` and any `Transactions.mcc_code` FK — category lives on the transaction itself now, no Visa MCC hop
- **`Transactions`** — now carries `category`, `merchant_key`, `normalized_description`, `resolution_source` (`user` | `global` | `bank` | `""`), `confidence`, still unique on `(upload, row_index)`
- **`MerchantResolution`** — per-user override table keyed `(user, merchant_key)`, durable storage.
- **`GlobalMerchantAlias`** — admin/seeded merchant to category map, unique on `merchant_key`, loaded from `global_merchant_aliases.json`
- **`Card_Products`** — added `is_catalog` (True = recommendable catalog product, False = user-created custom wallet card with zero reward rules)
- **`User_cards` / `Uploads` / `Reward_Rules`** — same roles as Day 2/3, wallet still owns the card a statement is attached to

### ***Services (business logic, not views):***
- **`csv_parser.py`** — only place that knows Chase column names, maps Chase Category to rewards category, blank payment/credit rows become `other`
- **`merchant_normalize.py`** — pure functions `merchant_key` / `normalized_display` (star processors, `#` store codes, web TLD strip)
- **`category_resolver.py`** — tiered resolve (Redis, then `MerchantResolution`, then global aliases, then bank, then unresolved `""`), in-process alias cache invalidated after seed
- **`merchant_cache.py`** — Redis L1 for *user* overrides only (`merchant:{user_id}:{merchant_key}`), fail-open if Redis is down
- **`upload_pipeline.py`** — parse, resolve once per distinct merchant, bulk create/update, returns coverage / needs_review
- **`card_catalog_ingestion.py`** — unchanged Day 3 path, plus stamps `is_catalog=True` on seed upserts

### ***Views + urls (HTTP surface):***
- **`POST /api/upload/`** — auth, file + `user_card_id`, hash idempotency, same bytes + different card returns **409** (must reassign, not silently rebind)
- **`GET /api/uploads/`** / **`POST /api/uploads/<id>/reassign/`** — list imports, move every tx on that statement to another wallet card
- **`GET /api/transactions/`** — your rows with `card_name`, `upload_id`, `filename` joined in
- **`GET /api/review/`** / **`POST /api/review/answer/`** — unresolved merchants by spend, answer upserts override, backfills category + stamps `resolution_source=user` / `confidence=1.0`, warms Redis
- **`GET /api/cards/`** — active catalog products (`is_catalog=True`) for wallet add / Day 5 scoring pool
- **`GET|POST /api/wallet/`** / **`DELETE /api/wallet/<id>/`** — own cards (catalog id *or* custom name/issuer/network), hard-delete cascades txs + empty uploads, orphan custom products cleaned up
- **`setup_dev`** — one command: seed cards + aliases, ensure `user1`, attach a wallet card, print credentials

### ***Data / ops files:***
- `reward_categories.json` — shared category buckets for resolver, review, and card rules
- `global_merchant_aliases.json` — seeded via `seed_global_merchants`
- Sample Chase CSVs under `data/sample_uploads/`, Postman collection + `workflows.md` for manual testing

# **DECISIONS MADE**
--------------------

### Category-native resolution over MCC + LLM
**Decision:** Store and resolve rewards categories directly. No MCC table, no LLM, no Visa/Plaid calls in the resolve path.

**Why:**
- Chase exports already give a rough category + merchant string — enough to categorize without hopping the complicated trail of MCC resolving.
- LLM/API pricing and free-tier limits eliminated per-transaction (or even per-merchant) calls out of contention
- One shared category list (`reward_categories.json`) ties statements, globals, user answers, and Day 5 reward rules together

### Never collapse `""` into `other`
**Decision:** Unresolved stays `""` and surfaces in the review queue. `other` is only for spend no card bonuses (fees, utilities, payments, etc.).

**Why:**
- Dumping unknowns into `other` hides gaps and poisons Day 5 scoring
- Review exists so the user fills real gaps, not so the pipeline pretends it knew

### User overrides beat bank and global (and stay per-user)
**Decision:** Tier order is Redis → `MerchantResolution` → `GlobalMerchantAlias` → bank → unresolved. Overrides are keyed `(user, merchant_key)`.

**Why:**
- The user is the authority on their own spend (Chase “Shopping” is a default, not a verdict)
- A global user-write table would let one person’s label rewrite everyone else’s categorization
- Redis is L1 for *user* answers only (fail-open). Globals live in Postgres + an in-process map, not Redis

### Exact `merchant_key` match, not fuzzy / semantic
**Decision:** Normalize first (`merchant_key()`), then exact lookup. No embeddings, no prefix guessing in v1.

**Why:**
- After normalize, keys are discrete tokens — fuzzy matching reintroduces false merges (e.g. similar brand prefixes)
- Deterministic, free, and testable. Coverage gaps are fixed by better normalize rules or more alias keys, not by guessing

### Bank categories stay in the adapter
**Decision:** Only `normalize_csv` knows Chase column names and Chase Category strings.

**Why:**
- Resolver and pipeline see canonical rows only
- Adding another bank later = one new adapter, not a rewrite of resolve / review / upload

### One statement, one wallet card — reassign is explicit
**Decision:** Same file hash + different `user_card_id` returns **409**. Wrong-card fixes go through `POST /api/uploads/<id>/reassign/`.

**Why:**
- Silent rebind on re-upload is an easy footgun (especially once Day 5 scores by card)
- Users still get a fix path without re-importing bytes
- Upload-level only (no per-row card edits) matches “a statement comes from one physical card”

### Catalog vs custom cards via `is_catalog`
**Decision:** Custom wallet cards create `Card_Products` with `is_catalog=False` and zero reward rules. `GET /api/cards/` only lists catalog products.

**Why:**
- Day 5 should score recommendable products, not invent rewards for free-text cards
- Users can still attach real statements to cards we don’t catalog yet

# **RESULTS OF DECISIONS**
--------------------------
- End-to-end path works offline: seed → wallet → upload Chase CSV → categorize via global/bank → review answer stamps `user` / `1.0` → re-upload same file refreshes in place
- Sample statements (including May) hit high / full coverage without any external API
- Wrong-card mistake is recoverable via uploads list + reassign, without silent spend moves
- Automated suite green last full run (**173** tests), including upload HTTP, review isolation, normalize, resolver (dead Redis fail-open), and wallet catalog/custom
- Manual verification path documented in `workflows.md` + Postman collection (auth inherit, upload, review, reassign)

# **THINGS TO REMEMBER**
------------------------
- `merchant_key` in aliases and overrides must match `merchant_key()` output (`AMTRAK`, not `AMTRAK .COM 1160…`)
- `""` = unresolved (review). `other` = real bucket (fees, utilities, payments). Never merge them
- Overrides are per-user. Redis caches user answers only. Globals are seed/admin data
- Same file + same card = refresh. Same file + different card = 409 → use reassign
- Custom wallet cards are `is_catalog=False` (not in Day 5 scoring pool). Catalog add uses `card_product_id`
- Re-upload after normalize/alias changes to rewrite stored keys on existing rows
- Ops truth: `workflows.md`. API shapes: Postman collection. Local boot: `setup_dev`

