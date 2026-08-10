# Cards

Monorepo for the Cards credit-card rewards project.

| Path | Role | Host |
|------|------|------|
| `backend/` | Django + DRF API | Render (Docker) |
| `frontend/` | Vite + React SPA | Vercel |
| `docs/` | Design notes and workflows | — |

## Local demo workflow

1. Start API: `docker compose up --build` → `http://localhost:8000`
2. Seed catalog (if empty): `docker compose exec web python manage.py seed_cards`
3. Start UI: `cd frontend && cp .env.example .env && npm install && npm run dev` → `http://localhost:5173`
4. Register → add wallet card → upload a CSV from `backend/data/sample_uploads/` → review (if needed) → dashboard → recommendations → transactions

## Frontend

```bash
cd frontend
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev
npm test
npm run build
```

Vercel: set project root to `frontend/`, set `VITE_API_BASE_URL` to the Render API origin, and keep `frontend/vercel.json` (SPA rewrites). After the Vercel URL exists, add that exact origin to Render `CORS_ALLOWED_ORIGINS`.

## Backend

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
python manage.py migrate
python manage.py test --settings=config.settings.test
```

Docker:

```bash
docker compose up --build
```

## CI

GitHub Actions (`.github/workflows/ci.yml`): backend tests, frontend `npm ci` → lint → test → build, Docker image build.

## Production URLs

Fill in after deploy:

- API (Render): _pending_
- UI (Vercel): _pending_

## Auth note

MVP stores JWTs in `sessionStorage`. Before real financial data, move the refresh token to a Secure HttpOnly cookie.
