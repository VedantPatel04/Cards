I am going to keep my documentation concise and easy to understand. 
Therefore I will keep my daily documentation to a maximum of 5 things:

# **CONTEXT OF THE PROBLEM**
----------------------------
- Define all core data models and enforce correctness at the DB level (not just in code)
- Create and apply migrations with idempotency constraints baked in
- Wire up the `POST /api/register/` endpoint
- Write model tests and constraint tests to verify DB behavior
- Set up the test harness (Django test runner + in-memory SQLite)

## **OVERVIEW OF CHANGES MADE**
-------------------------------

### ***Data Models (dependency order):***
- `CustomUser` — extends `AbstractUser`; `email` is unique and required
- `Card_Products` — card catalog entry; unique per `(name, issuer)`
- `Reward_Rules` — FK to `Card_Products`; unique per `(card_product, category)`
- `User_cards` — FK to `CustomUser` + `Card_Products`; unique per `(user, card)`
- `Uploads` — FK to `CustomUser`; unique per `(user, file_hash)` → idempotent ingestion
- `MCC_Codes` — PK is `code` (not `id`); maps merchant category codes to reward categories
- `Transactions` — FK to `Uploads` + `User_cards` + `MCC_Codes`; unique per `(upload, row_index)` → prevents duplicate rows from the same file

### ***Migrations:***
- All seven models migrated and applied to Postgres
- Fixed a model/migration drift: `Card_Products (name, issuer)` unique constraint was defined in the model but missing from the initial migration — added `0002_alter_card_products_unique_together`
- Fixed `Card_Products.updated_at`: was `auto_now_add` (set once, never updated); corrected to `auto_now`

### ***Registration Endpoint `POST /api/register/`:***
- `RegisterSerializer` — validates username, email, password, password confirmation; hashes password via `create_user()`
- `register` view — public (`AllowAny`), returns `201` with safe `UserSerializer` (no password fields)
- `urls.py` was already wired; the view was missing and caused an `ImportError` on startup — now resolved

### ***Test Harness:***
- `config/settings/test.py` uses in-memory SQLite (`:memory:`) so tests never touch the dev DB
- Added `apps/__init__.py` — `apps/` was a namespace package; without it, test discovery silently found 0 tests and module names collided across apps
- `backend/seeds.py` — shell testing module, allows for a quick, manual seeding of database (`make_user`, `make_card`, `make_reward_rule`, `make_user_card`, `make_upload`, `make_mcc`, `make_transaction`)run-scoped counters keep auto-generated unique fields collision-free

### ***Tests (21 passing):***
- **Registration** — creates non-superuser, password is hashed, response doesn't expose password, rejects mismatched passwords, rejects duplicate username, rejects duplicate email, endpoint is public (no token required)
- **Constraint: `Card_Products (name, issuer)`** — duplicate rejected; same name different issuer allowed
- **Constraint: `Reward_Rules (card_product, category)`** — duplicate rejected; same category different card allowed
- **Constraint: `User_cards (user, card)`** — duplicate rejected; same card different user allowed
- **Constraint: `Uploads (user, file_hash)`** — duplicate rejected; same hash different user allowed
- **Constraint: `Transactions (upload, row_index)`** — duplicate rejected; same row_index different upload allowed
- **MCC_Codes** — `code` is PK, duplicate code rejected, `on_delete=PROTECT` blocks deleting an MCC referenced by a transaction
- **`Card_Products.updated_at`** — verifies it actually changes on `save()`

### Run all tests with:
```
python manage.py test --settings=config.settings.test
```

# **DECISIONS MADE**
--------------------
### Idempotency via DB constraints
Unique constraints live in the schema (`unique_together`, PK on `MCC_Codes.code`) so re-runs of data insertion scripts / user actions can't create duplicates

### `MCC_Codes.code` as primary key (not `id`)
MCC codes are a fixed external standard — the code itself is the identity. Using `code` as PK avoids a redundant surrogate key and makes FK references (`Transactions.mcc_code`) self-documenting.

### `on_delete=PROTECT` on `Transactions.mcc_code`
MCC codes are reference data. Accidentally deleting a category code that transactions reference would corrupt the data. `PROTECT` makes the DB refuse the delete rather than silently cascading.

# **RESULTS OF DECISIONS**
--------------------------
- All constraints verified by tests that assert `IntegrityError` on violation
- `POST /api/register/` creates a regular user account, verified in Postman

# **THINGS TO REMEMBER**
------------------------
- Always run tests with `--settings=config.settings.test` (uses SQLite in-memory; default settings point at local Postgres)
- `seeds.py` is a test-only utility — do not import it from production code
- `User_cards` is required before transactions can be recorded — a user must add a card to their wallet before uploading a statement
