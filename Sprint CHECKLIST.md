# Sprint 1 Timeline (1 week · 2–3 hrs/day)

**Project:** Django + DRF REST API — backend for a live product with real users.  
**Sprint 1 scope:** Backend API only. Frontend (React) is Sprint 2.  
**Key constraints:** SimpleJWT auth, user registration endpoint, idempotent ingestion + uploads, tests baked in, API verified via Postman before frontend begins.

---

## Day 0 — Sprint Plan + Technical Decisions
**Checkpoint:** You can explain the project in 60 seconds and your core contracts won’t change.

- Lock MVP scope (what’s in / out)
- Lock response shapes:
  - `/summary` output
  - `/recommendations` output
- Lock MVP categories (small fixed set)
- Draft DB entities + constraints (especially idempotency)
- Create sprint board (10–20 tasks max)

**Deliverable:**  
- `docs/sprint-1-plan.md`  
- `docs/data-model.md`

---

## Day 1 — Foundation + Authentication (SimpleJWT)
**Checkpoint:** Running API with protected endpoints.

- Django project + DRF configured
- Postgres wired up
- SimpleJWT installed and issuing tokens
- `POST /api/register/` — creates a regular (non-superuser) user account
- Protected “ping” endpoint proves auth works
- Test harness working (pytest or Django test runner)

**Deliverable:**  
- Auth flow working in Postman (register → login → access protected endpoint)
- Baseline tests passing

---

## Day 2 — Data Models + Migrations (Idempotency Designed In)
**Checkpoint:** Database enforces correctness (not “careful coding”).

**Tables (in dependency order):**
- `USERS` — PK: id (via AbstractUser)
- `CARD_PRODUCTS` — PK: id
- `REWARD_RULES` — PK: id, FK: card_product_id
- `USER_CARDS` — PK: id, FK: user_id + card_product_id
- `UPLOADS` — PK: id, FK: user_id → idempotent ingestion
- `MCC` — PK: code (not id) → contains MCC mapping
- `TRANSACTIONS` — PK: id, FK: upload_id + user_card_id + mcc_code

**Registration Endpoint**
- creates new user by calling `create_user()`

**Constraints:**
- `REWARD_RULES`: unique per `(card_product, category)`
- `TRANSACTIONS`: unique per `(upload, row)` or equivalent
- `USER_CARDS`: referenced by `REWARD_RULES` in a minor manner

- Seed a tiny test dataset for fast testing

**Deliverable:**  
- Migrations created + applied  
- Model tests passing
- Endpoint successfull creates new user upon request  
- Constraints verified

---

## Day 3 — Card Catalog Ingestion (Local Snapshot → DB)
**Checkpoint:** Card catalog can be populated repeatedly without duplicates.

- Build ingestion command/service that loads your local snapshot into `Card` + `RewardRule`
- Ensure re-running ingestion is safe (idempotent)
- Tests prove: “run twice == same DB state”

**Deliverable:**  
- Ingestion works  
- Idempotency tests pass

---

## Day 4 — Upload Pipeline (CSV → Transactions, Idempotent)
**Checkpoint:** Upload results in stored transactions owned by the authenticated user.

- Upload endpoint creates an `Upload` record
- CSV parser converts rows → transactions + categories
- Duplicate upload handling prevents duplicates
- Tests cover parsing + idempotency + auth scoping

**Deliverable:**  
- Upload works end-to-end via Postman

---

## Day 5 — Spend Summary Endpoint
**Checkpoint:** Summary numbers are correct and test-verified.

- Aggregation service (ORM sums/grouping)
- `/summary` endpoint returns totals by category
- Tests use a small “truth dataset” with known totals

**Deliverable:**  
- Correct summary output  
- Tests that catch regressions

---

## Day 6 — Recommendation Engine + Endpoint
**Checkpoint:** Recommendations are explainable and stable.

- Scoring service ranks cards using reward rules + spend totals
- Deduct annual fee in value estimate
- `/recommendations` returns top 3 + explanation
- Tests validate ranking behavior on known data

**Deliverable:**  
- Recommendations working in Postman  
- Ranking tests pass

---

## Day 7 — Hardening + Demonstration
**Checkpoint:** Confident demo + repo reads like a professional project.

- Permissions audit: users only access their own uploads/transactions
- Better error messages + validation
- README polished:
  - setup
  - ingestion
  - upload
  - summary
  - recommendations
  - Postman steps
- End-to-end demo script (repeatable)

**Deliverable:**  
- “Fresh clone → working demo” without guesswork

---

## Sprint 1 Non-Negotiables
- Auth required on `/upload`, `/summary`, `/recommendations`
- Idempotency enforced by DB constraints (not just code)
- Service layer for parsing/aggregation/scoring (views stay thin)
- Tests written as you go (not at the end)
- Postman demo flow works by sprint end
