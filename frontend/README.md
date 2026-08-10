# Cards frontend

Vite + React + TypeScript SPA. Deploy root on Vercel: `frontend/`.

## Local

```bash
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

Requires the backend API on `:8000` with CORS allowing `http://localhost:5173`
(see root `docker-compose.yml`).

## Scripts

- `npm run dev` — Vite dev server
- `npm run build` — typecheck + production build
- `npm run lint` — oxlint
- `npm run preview` — preview production build
