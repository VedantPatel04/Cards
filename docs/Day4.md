# **CONTEXT OF THE PROBLEM**

API pricing - A huge blocker that eventually led to the complete restructuring of our category resolution architecture.

API's aren't cheap and running even just a tens or hundreds of calls over thousands of transactions becomes expensive if you're limited to the free tiers like I am (assuming the free tier hands out that much usage to begin with). 

### What's the real issue here?

```
I need a way to resolve merchant categories without making calls to any API, whether that be for an LLM or VISA developers or PLAID  ,,, you get the point.
```



### Solution

```
A new architecture that relies on a couple of things:

- A global preseeded dataset from data gathered through official merchant category code lists and other mappings published by networks and issuers like VISA, MasterfCard, Chase, etc.

- Category supplied by bank transaction statements

- User supplied data for any unresolved categories

```

## **OVERVIEW OF CHANGES MADE**

---

Creating MCC retrieval functionality using Redis exact-matching (No RDB, AOF only L1 caching) + persistent DB table caching MerchantResolution class.

Use a fallback logic for any MCC that isn't mapped.

# **DECISIONS MADE**
---
- **Normalize the merchant key first:** collapses "MCDONALD'S F31398"/"F25696" → "MCDONALDS" so rules + caching actually hit (16 Chase rows → ~5 unique merchants)

&nbsp;
- **Exact caching, NOT semantic:** after normalization keys are discrete tokens (nothing for semantics to absorb); semantic would re-add a per-lookup embedding cost AND mis-merge different-MCC merchants (CHEVRON gas 5541 vs EXTRAMILE 5499). Exact-match can't make that mistake.

&nbsp;
- **Redis (speed) + MerchantResolution (persistence):** Redis = in-memory L1 cache, 
O(1) lookup time with a TTL, skips a DB round-trip on repeats. `MerchantResolution` (Postgres) = durable source of truth so LLM results survive a cache flush. 

&nbsp;
- **Adapter pattern:** `normalize_csv()` is the only place Chase columns live; resolver/pipeline see canonical rows, so Plaid later = one new adapter


# **RESULTS OF DECISIONS**

---

FILL in later.



# **THINGS TO REMEMBER**

---

- `merchant_rules.json` keys must be the **normalized** form ("WAL MART", not "WAL-MART #2297")
- Tier-5 categories must match the `seed_mcc` / `card_catalog.json` vocabulary exactly
- Cache a `""` sentinel for known-unknowns so the LLM isn't re-hit for prior failures
- Budget cap belongs in the pipeline (stateful across rows), not `llm_client.py`
- `LLM_API_KEY` in `.env` only; don't `makemigrations` until `MerchantResolution` has real fields (currently `pass`)

