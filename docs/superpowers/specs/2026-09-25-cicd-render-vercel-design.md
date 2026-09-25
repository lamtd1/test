# CI/CD: Render (backend) + Vercel (frontend)

Status: approved (2026-09-25)

## Context

`test/` was just extracted into its own git repo (`github.com/lamtd1/test`,
previously nested inside the home-directory repo by accident). It has no
deploy pipeline yet: `Dockerfile` and `docker-compose.yml` are empty stubs,
the frontend hardcodes `http://localhost:8000` as its API base, and CORS on
the backend only allows `localhost:5173`.

Goal: push-to-deploy for both services, plus a CI gate that catches broken
code before merge. Database stays SQLite for now (see ADR 0004) — no
Postgres/Supabase migration in this pass.

## Decisions

1. **Backend hosting: Render**, via native GitHub integration (not GitHub
   Actions deploy). `render.yaml` (Blueprint) defines the service so setup
   is one import, not manual dashboard clicking.
2. **DB: keep SQLite, reseed on every boot.** Render's start command runs
   `python scripts/seed.py && uvicorn src.main:app --host 0.0.0.0 --port
   $PORT`. No persistent disk. Every cold start/redeploy = clean demo
   state. Documented as ADR 0004 (alternative considered: migrate to
   Supabase Postgres now — deferred, see ADR for why).
3. **Frontend hosting: Vercel**, via native GitHub integration, root
   directory `web/`. Vercel builds preview deployments on PRs and
   production on `main` automatically once the repo is imported — no
   GitHub Actions step needed for the deploy itself.
4. **Frontend → backend wiring**: `web/src/lib/api.ts`'s hardcoded `BASE`
   becomes `import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1"`.
   `VITE_API_URL` is set as a Vercel project env var pointing at the Render
   service URL.
5. **CORS**: `src/main.py`'s `allow_origins` reads from a `CORS_ORIGINS`
   env var (comma-separated, falls back to the two localhost origins) so
   the Vercel domain can be allow-listed without a code change.
6. **CI gate** (`.github/workflows/ci.yml`), runs on push and PR to `main`:
   - backend job: `ruff check .`, `pytest`
   - frontend job: `npm ci`, `tsc -b`, `oxlint`
   This blocks nothing by itself; branch protection (below) is what makes
   it a gate.
7. **Branch protection on `main`**: require the CI workflow's checks to
   pass before merging (configured via `gh api` on the `lamtd1/test` repo
   settings, since the user approved this in-chat).

## Out of scope (this pass)

- Migrating SQLite → Supabase/Postgres (ADR 0004 explains the deferral).
- `finance_purged_at` deletion endpoint, feedback UI wiring, sale
  `add_unit` endpoint (pre-existing "chưa làm" items, unrelated to CI/CD).
- Staging environments / preview-env-per-PR for the backend (Render
  Blueprints support this later if needed).

## Files touched

- `Dockerfile` (fill in — currently empty)
- `render.yaml` (new)
- `.github/workflows/ci.yml` (new)
- `src/main.py` (CORS env var)
- `web/src/lib/api.ts` (API base env var)
- `web/.env.example` or similar (document `VITE_API_URL`)
- `docs/adr/0004-sqlite-reseed-on-render.md` (new)
- `README.md` (deploy section: how to connect Render/Vercel dashboards,
  since that step can't be automated from here)

## Testing

- CI workflow itself is the test: push a commit, confirm both jobs run
  and pass on a currently-green tree.
- Manual: after Render/Vercel are connected (user does this in their
  dashboards, steps documented in README), hit the deployed frontend,
  run the happy-case chat flow end-to-end against the deployed backend.
