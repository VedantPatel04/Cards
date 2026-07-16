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

### ***Ingestion service (`services/card_ingestion.py`):***
- TODO

### ***Management command (`apps/cards/management/commands/seed_cards.py`):***
- TODO

### ***Tests:***
- TODO

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
- Business logic lives in `services/card_ingestion.py`, the management command is a thin wrapper that calls it
- A plain function is easier to test (call it directly) than a command (requires Django's `call_command` machinery)

### Natural keys drive idempotency
- `Card_Products` natural key: `(name, issuer)` — two cards are "the same" if they share both
- `Reward_Rules` natural key: `(card_product, category)` — a card can only have one rule per category
- These are the `update_or_create` lookup kwargs; everything else goes in `defaults=`

# **RESULTS OF DECISIONS**
--------------------------
- TODO (fill in after implementation)

# **THINGS TO REMEMBER**
------------------------
- Category strings in `card_catalog.json` must be identical to what `seed_mcc` assigns — a mismatch means the recommendation engine silently misses matches
- `Active Cash` has no reward rules (flat 2% base rate on everything) — this is correct, not a bug
- Reward rates with annual caps (e.g. Amex Blue Cash Preferred 6% groceries capped at $6k/year) are stored as flat rates for MVP — the cap logic is deferred
