I am going to keep my documentation concise and easy to understand.
Therefore I will keep my daily documentation to a maximum of 5 things:

# **CONTEXT OF THE PROBLEM**
----------------------------
- Rank catalog cards from the user's spend summary (recommendations endpoint) — Day 6
- Deploy a live backend: settings/secrets, Docker, CI, Render + Supabase — Day 7

## **OVERVIEW OF CHANGES MADE**
-------------------------------

### ***Day 6 — Recommendations:***
- Recommendation engine scores catalog cards from the spend summary; view stays thin
- Recommendations endpoint returns top 5 (USD per year), plus confidence and value basis
- Inputs: annualized → spending score; by category → signup bonus; coverage → confidence
- Total score = spending score − annual fee + signup bonus score
- Bonus statuses: met, not met, insufficient data, or no bonus
- Covered by tests and the demo flow script; see workflows.md sections 7–8

### ***Day 7 — Hardening + deploy:***
- Months covered = distinct months with transactions — see Day 5
- Settings split into base / local / test / production (see `settings-architecture.md`)
- Docker image cards-web: migrate + Gunicorn; compose up --build serves on port 8000
- CI runs tests (Python 3.12) and builds the image
- Live: Render web + Redis; Supabase Postgres via session pooler with SSL

# **DECISIONS MADE**
--------------------
- **Don't swap score inputs** — annualized for rewards, actual category totals for bonuses
- **Negative totals OK** — when the fee beats rewards, show it ... headline and break-even explain why
- **Supabase = Postgres only** — Django + JWT own auth, don't auto-expose tables
- **Compose rehearses prod, SSL off via env** — local Postgres has no TLS, Render keeps SSL on
- **Session pooler on Render** — direct is IPv6-fragile, transaction pooler fights long-lived connections
- **CI builds, does not deploy** — secrets stay in Render/Supabase

# **RESULTS OF DECISIONS**
--------------------------
- Recommendations endpoint + tests/demo pass
- Local compose and the live Render API both work
- Root URL 404 is normal — hit API routes instead

# **THINGS TO REMEMBER**
------------------------
- Don't swap annualized and by-category inputs when scoring
- Allowed hosts must match the exact Render hostname, percent-encode special chars in the DB password
- Compose turns DB SSL off - leave it unset on Render (SSL on)
- backend/.env is for the host only — compose injects its own env
- Wire CORS/CSRF when Sprint 2 has a frontend origin

---

**End of Sprint 1.** Backend API shipped (auth -> recommendations, Docker, CI, live URL).

**Next: Sprint 2** — Vite/React on Vercel against this API.
