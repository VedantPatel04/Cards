# Cards — Frontend

Vite + React + TypeScript SPA. Vercel deployment root: `frontend/`.

## Local

```bash
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev            # http://localhost:5173
```

Requires the backend on `:8000` with CORS allowing `http://localhost:5173` (see root `docker-compose.yml`).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run build` | Type-check + production build |
| `npm run lint` | oxlint |
| `npm test` | Vitest unit + UI tests |
| `npm run preview` | Preview production build |
