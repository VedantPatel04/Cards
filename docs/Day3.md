I am going to keep my documentation concise and easy to understand. 
Therefore I will keep my daily documentation to a maximum of 5 things:

# **CONTEXT OF THE PROBLEM**
----------------------------
- Build an ingestion service + management command that loads the local card catalog snapshot into `Card_Products` + `Reward_Rules`
- Ensure re-running is safe (idempotent) — no duplicates, no errors on repeated runs
- DB Update when the snapshot changes: deactivate removed cards, delete stale reward rules
- Validate the input file before touching the DB, clear Error Messages displayed for debugging
- Verify with tests: "run twice == same DB state"

## **OVERVIEW OF CHANGES MADE**
-------------------------------

### ***Card catalog snapshot (`data/card_catalog/card_catalog.json`):***
- Manually curated snapshot of 4 real cards: Chase Sapphire Preferred, Chase Freedom Unlimited, Amex Blue Cash Preferred, Wells Fargo Active Cash
- Each entry contains all `Card_Products` fields + a nested `reward_rules` list
- Categories use the fixed vocabulary: `dining`, `groceries`, `travel`, `gas`, `entertainment`, `shopping`, `other` — must match MCC category mappings exactly for the recommendation engine to work
- Decimal fields stored as JSON strings, not floats — avoids float rounding errors when parsed into Python `Decimal`

### ***Ingestion service (`services/card_catalog_ingestion.py`):***
- `load_card_catalog()` — reads + parses `card_catalog.json`; path anchored to `settings.BASE_DIR` so it works regardless of the caller's working directory; shared between ingestion and tests (single source of truth)
- `_validate_catalog()` — called before any DB write; checks all required keys exist and all decimal fields are parseable; raises `ValueError` with the exact field name if anything is wrong; empty-file check prevents a blank snapshot from deactivating the entire catalog
- `ingest_card_catalog()` — wrapped in `@transaction.atomic`; returns a summary dict of created/updated/deleted/deactivated counts
  - Outer loop: upserts each `Card_Products` row; collects `processed_card_ids`
  - Inner loop: upserts each `Reward_Rules` row for the current card; collects `snapshot_categories`
  - After inner loop: hard-deletes any `Reward_Rules` for that card whose category is no longer in `snapshot_categories` (stale rule cleanup)
  - After outer loop: `update(is_active=False)` on any `Card_Products` row not in `processed_card_ids` (removed-card soft-delete)

### ***Management command (`apps/cards/management/commands/seed_cards.py`):***
- Thin wrapper around `ingest_card_catalog()` — no logic here
- Prints the summary dict in green on success; prints the `ValueError`/`FileNotFoundError` message in red on failure without a raw traceback
- Run with: `python manage.py seed_cards`

### ***Tests (17 passing in `apps/cards/tests.py`):***
- **Idempotency** — two runs produce identical counts; no hardcoded numbers
- **Correctness** — loops over the real JSON file and asserts every field on every card + every reward rule matches the DB exactly (auto-covers new cards added to the snapshot later)
- **Update-in-place (cards + rules)** — mutate a field directly in the DB, re-run, assert it's restored and no duplicate row was created
- **Validation** — missing key, invalid decimal, and empty catalog each raise `ValueError` with the right message; atomic rollback leaves the DB at 0 rows on any validation failure
- **Reconciliation** — removed card gets `is_active=False` but its row survives (FK safety); stale reward rule is deleted when its category is dropped from the snapshot
- **Summary dict** — return value contains all expected keys; `cards_created` equals catalog length on a fresh DB

### ***Hand verification (Postgres, cross-checked with `psql`):***
- `python manage.py seed_cards` → `cards: 4 created, 0 updated, 0 deactivated | rules: 11 created, 0 updated, 0 deleted`
- Second run → `cards: 0 created, 4 updated, 0 deactivated | rules: 0 created, 11 updated, 0 deleted`
- Confirmed same counts independently via raw `psql` queries — bypasses the ORM entirely

# **DECISIONS MADE**
--------------------

### Snapshot-based card catalog over scraping
**Decision:** Card data is maintained as a manually curated local snapshot, not scraped on demand.

**Why:**
- Reward structures change rarely (quarterly at most) — a real-time scraper is over-engineering
- Scraping is brittle (HTML changes silently break it), slow, and often against a site's ToS
- Snapshot acts as a clean boundary: ingestion reads a local file and never touches the network

```
[ ACQUISITION ]                  [ BOUNDARY ]              [ INGESTION ]
manual curation / future feed  →  card_catalog.json  →  seed_cards command  →  DB
  (done periodically,              (clean, versioned,       (idempotent,
   outside the app)                 under our control)       offline, tested)
```

**Future work:** replace manual curation with a scheduled job (cron / GitHub Action) that produces the same JSON shape. Ingestion stays unchanged.

### Service function + thin command (not raw command logic)
- All logic in `services/card_catalog_ingestion.py` — callable directly from tests without `call_command`
- Management command is a 27-line wrapper that calls the function and handles output/errors

### Natural keys drive idempotency
- `Card_Products` natural key: `(name, issuer)`
- `Reward_Rules` natural key: `(card_product, category)`
- Lookup kwargs only; everything mutable goes in `defaults=` — a field in the lookup instead of defaults was an actual bug caught during development that caused duplicate rows on re-runs

### Soft-delete cards, hard-delete stale rules
- **Cards removed from snapshot** → `is_active=False` (not deleted) — `User_cards` FKs to `Card_Products`; hard-delete would cascade-delete wallet entries
- **Reward rules removed from snapshot** → hard-deleted — `Transactions` does not FK to `Reward_Rules`, so it's safe; leaving stale rules would corrupt recommendation scoring

### Validate before writing (fail-fast with context)
- `_validate_catalog()` runs before `@transaction.atomic` touches the DB
- Error messages name the exact card and field that failed — not a raw `KeyError`
- Empty-catalog guard prevents a blank file from silently deactivating every card

### Tests read the same file ingestion reads
- `load_card_catalog()` is a shared function — tests call it to get expected values instead of hardcoding literals
- `unittest.mock.patch` injects bad catalogs into tests without touching any files on disk

# **RESULTS OF DECISIONS**
--------------------------
- `python manage.py seed_cards` works end-to-end; run 1 creates, run 2 updates — counts identical, confirmed via `psql`
- All 17 tests pass; validation, reconciliation, and idempotency tests each confirmed to have real teeth via deliberate bug injection
- Service is decoupled from the command — callable from the shell, tests, or any future caller without Django's management machinery

# **THINGS TO REMEMBER**
------------------------
- Category strings in `card_catalog.json` must be identical to what `seed_mcc` assigns — a mismatch means the recommendation engine silently misses reward rule matches
- `Active Cash` has no reward rules (flat 2% base rate on everything) — this is correct, not a bug
- Reward rates with annual caps (e.g. Amex Blue Cash Preferred 6% groceries capped at $6k/year) are stored as flat rates for MVP — cap logic deferred to a later sprint
- Always clean up manually-ingested dev DB rows after hand verification — `Card_Products.objects.filter(...).delete()` cascades to `Reward_Rules` automatically
- `is_active=True` is set explicitly in `update_or_create` defaults — this re-activates a previously deactivated card if it comes back in the snapshot

**Additional Thoughts**
------------------------
- Rewire ingestion logic to automatically consume currently available cards using GitHub jobs, maybe add scraping logic ...