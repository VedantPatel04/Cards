# Cards

Monorepo for the Cards credit-card rewards project.

| Path | Role | Planned Host |
|------|------|----------------|
| `backend/` | Django + DRF API | Render (Docker) |
| `frontend/` | Vite app (Sprint 2) | Vercel |
| `docs/` | Design notes and workflows | — |

## Backend quick start (host machine)

```bash
cd backend
cp .env.example .env   # set DATABASE_URL, REDIS_URL, etc.
# with venv active:
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Tests:

```bash
cd backend
python manage.py test --settings=config.settings.test
```

## Docker (local backend stack)

See comments in `docker-compose.yml`, `backend/Dockerfile`, and `backend/entrypoint.sh`.

```bash
docker compose up --build
```

API: `http://localhost:8000` (SSL redirect disabled in compose).

## Environment

- `backend/.env` — local Django / secrets (gitignored)
- `backend/.env.example` — documented keys
- Production secrets are set on Render; never commit them

Auth remains Django + SimpleJWT for now.
