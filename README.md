# Cards

### Hi friend / recruiter / peer / stalker :P

Is your Chase credit card expiring soon and you can't find the right one to sign up for next? 

This platform ranks the best credit cards available in August 2026 against your real spending - organized by categories - so you can pick your next favorite credit card!

Upload Chase transaction statements and get ranked credit card recommendations.

[Check out the product here!](https://newcardforme.vercel.app/) 

P.S. sadly backend servers need a minute to warm-up after hitting "login" or "register" b/c of Render free tier limits  

[API Swagger Docs](https://cards-api-ke5n.onrender.com/api/docs/)
## Tech stack

| Layer | Tools |
| --- | --- |
| Backend | Django 6, DRF, PostgreSQL, Redis |
| Frontend | React 19, TypeScript, Vite, Tailwind |
| Deploy | Render (API + Redis), Supabase (Postgres), Vercel (UI) |

---

## CI

GitHub Actions on every push and PR (`.github/workflows/ci.yml`):

- Backend: tests with coverage, Docker image build
- Frontend: lint (oxlint) · Vitest · Vite production build

---

## Project structure

```
backend/    Django API — apps/, services/, config/
frontend/   Vite + React SPA
docs/       Local setup + deploy, workflows, architecture, Postman
scripts/    End-to-end demo of just the backend endpoints (demo_flow.sh)
```

Local development and deploying: [docs/development.md](docs/development.md)
