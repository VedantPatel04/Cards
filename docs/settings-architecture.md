# Settings split (`config/settings/`)

**Modules**

| Module | Role |
|--------|------|
| `base.py` | Shared apps, middleware, DRF/JWT, Redis, CORS list parsing |
| `local.py` | Dev: `DEBUG=True`, `DATABASE_URL` (no SSL), local secret fallback |
| `test.py` | SQLite `:memory:`, Redis DB 15, registers `tests` app |
| `production.py` | `DEBUG=False`, required env secrets, `DATABASE_URL` with SSL, proxy SSL headers |

**Which module loads**

```bash
export DJANGO_SETTINGS_MODULE=config.settings.local        # host-based day-to-day
export DJANGO_SETTINGS_MODULE=config.settings.test         # tests / CI
export DJANGO_SETTINGS_MODULE=config.settings.production   # Docker / Render
```

Defaults: `manage.py` → `local`; `wsgi.py` / `asgi.py` → `production`.

**Database**

Local and production both use `DATABASE_URL` (via `dj-database-url`). Production defaults `DATABASE_SSL_REQUIRE=true` (Supabase/Render); docker-compose sets it to `false` for the local Postgres image. Do not manage the same tables with both Django migrations and Supabase SQL migrations — Django owns the schema.

**CORS**

`CORS_ALLOWED_ORIGINS` is a comma-separated env var. Default is empty until a frontend origin exists.
