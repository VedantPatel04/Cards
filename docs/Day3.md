I am going to keep my documentation concise and easy to understand. 
Therefore I will keep my daily documentation to a maximum of 5 things:

# **CONTEXT OF THE PROBLEM**
----------------------------
- Build an ingestion command that loads the local card catalog snapshot into `Card_Products` + `Reward_Rules`
- Ensure re-running the command is safe (idempotent) — no duplicates, no errors
- Verify with tests: "run twice == same DB state"

## **OVERVIEW OF CHANGES MADE**
-------------------------------

### ***Card catalog snapshot (`data/card_catalog/card_catalog.json`):***
- Created a manually curated snapshot of 4 real cards: Chase Sapphire Preferred, Chase Freedom Unlimited, Amex Blue Cash Preferred, Wells Fargo Active Cash
- Each entry contains all `Card_Products` fields + a nested `reward_rules` list
- Categories used are the fixed vocabulary: `dining`, `groceries`, `travel`, `gas`, `entertainment`, `shopping`, `other` — must match MCC category mappings exactly for the recommendation engine to work
- Decimal fields (`annual_fee`, `reward_rate`, etc.) are stored as JSON strings, not floats — avoids float rounding errors when parsed into Python `Decimal`

### ***Ingestion service (`services/card_catalog_ingestion.py`):***
- `load_card_catalog()` — reads + parses `card_catalog.json`; path anchored to `settings.BASE_DIR` so it works regardless of the caller's working directory
- `ingest_card_catalog()` — wrapped in `@transaction.atomic`; nested loop upserts each `Card_Products` row, then each of its `Reward_Rules` using the returned card object as the FK
- `update_or_create()` natural keys: `(name, issuer)` for cards, `(card_product, category)` for rules — everything else (fee, rate, network, etc.) lives in `defaults` only, so re-runs update in place instead of inserting duplicates

### ***Tests (9 passing in `apps/cards/tests.py`):***
- **Idempotency** — running ingestion twice produces identical `Card_Products`/`Reward_Rules` counts
- **Correctness** — loops over every entry in the *actual* JSON file and asserts every field on every card + every reward rule matches what's in the DB (no hardcoded card names/fees — reads the same file ingestion reads, so it can never drift out of sync)
- **Update-in-place (cards)** — mutate a card's `network` directly in the DB, re-run ingestion, assert it's overwritten back to the snapshot value and no duplicate row was created
- **Update-in-place (reward rules)** — same proof for `reward_rate`, which is the exact field that would silently duplicate rows if it were ever placed in the `update_or_create` lookup filter instead of `defaults`
- Plus the pre-existing `Card_Products`/`Reward_Rules` uniqueness constraint tests and the `updated_at` timestamp test from Day 2

### ***Hand verification (Postgres, cross-checked with `psql`):***
- Ran `ingest_card_catalog()` via `manage.py shell` against real Postgres → 4 cards, 11 reward rules
- Independently confirmed the same counts with raw SQL (`psql -d cards_db -c "SELECT COUNT(*) FROM cards_card_products;"`) — bypasses the ORM entirely
- Re-ran ingestion 2 more times (3 runs total) → counts stayed at 4 cards / 11 reward rules both in the ORM and in `psql`
- Eyeballed `SELECT name, issuer, network, annual_fee FROM cards_card_products;` — all 4 cards present with correct data

# **DECISIONS MADE**
--------------------

### Snapshot-based card catalog over scraping

**Decision:** Card data is maintained as a manually curated local snapshot (`data/card_catalog/card_catalog.json`) that is periodically updated by hand, not scraped on demand.

**Why:**
- Reward structures change rarely (quarterly at most) — a real-time scraper is over-engineering for data that barely moves
- Scraping is brittle (HTML changes silently break it), slow, and often against a site's ToS
- A clean snapshot file acts as a boundary: ingestion reads a local file and never touches the network, making it fast, testable, and runnable offline

**The model:**
```
[ ACQUISITION ]                  [ BOUNDARY ]              [ INGESTION ]
manual curation / future feed  →  card_catalog.json  →  seed_cards command  →  DB
  (done periodically,              (clean, versioned,       (idempotent,
   outside the app)                 under our control)       offline, tested)
```

**Future work:** If catalog size grows beyond ~50 cards, replace the manual acquisition step with a scheduled job (cron / GitHub Action) that scrapes or calls a data feed, normalizes the output to this same JSON shape, and writes the snapshot. Ingestion stays unchanged.

### Service function, not raw command logic
- Business logic lives in `services/card_catalog_ingestion.py`; no management command was needed since the function is directly callable from the shell/tests
- A plain function is easier to test (call it directly) than a command (requires Django's `call_command` machinery)

### Natural keys drive idempotency
- `Card_Products` natural key: `(name, issuer)` — two cards are "the same" if they share both
- `Reward_Rules` natural key: `(card_product, category)` — a card can only have one rule per category
- These are the `update_or_create` lookup kwargs; everything else goes in `defaults=` — putting a mutable field (e.g. `reward_rate`) in the lookup instead of `defaults` was an actual bug caught during development: it made re-runs insert duplicate rows instead of updating, since the old rate no longer matched the lookup filter

### Tests read the same file ingestion reads (no hardcoded fixture values)
- `load_card_catalog()` is a shared function — both ingestion and tests call it
- Tests loop over the real JSON and assert the DB matches it field-by-field, instead of hardcoding `"Sapphire Preferred"` / `"95.00"` etc. as separate literals
- This means the test suite automatically covers new cards added to the catalog later, and never goes stale relative to the snapshot

# **RESULTS OF DECISIONS**
--------------------------
- `ingest_card_catalog()` runs cleanly using Postgres: 4 cards, 11 reward rules, confirmed independently via `psql`
- 3 consecutive runs produce identical row counts — idempotency holds in practice, not just in the test suite
- All 9 tests pass; the ingestion-specific tests were confirmed to have real teeth by deliberately reintroducing two known bugs (rate in lookup filter, swapped field mapping) and watching both fail with the expected `IntegrityError` / `AssertionError` before reverting

# **THINGS TO REMEMBER**
------------------------
- Category strings in `card_catalog.json` must be identical to what `seed_mcc` assigns — a mismatch means the recommendation engine silently misses matches
- `Active Cash` has no reward rules (flat 2% base rate on everything) — this is correct, not a bug
- Reward rates with annual caps (e.g. Amex Blue Cash Preferred 6% groceries capped at $6k/year) are stored as flat rates for MVP — the cap logic is deferred
- Always clean up manually-ingested rows from the dev DB after hand verification (`Card_Products.objects.filter(name__in=[...]).delete()` — `Reward_Rules` cascade-delete automatically)
