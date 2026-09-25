# CI/CD (Render + Vercel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `git push` to `main` auto-deploy the backend to Render and the frontend to Vercel, with a CI gate (lint + tests) blocking broken merges.

**Architecture:** Render and Vercel each watch the GitHub repo natively and deploy on push — no deploy step lives in GitHub Actions. GitHub Actions' only job is the CI gate (ruff/pytest/tsc/oxlint) plus branch protection making that gate mandatory. Backend keeps SQLite; the Docker start command reseeds it from `data/*.csv` on every boot so every deploy comes up in a known-good demo state (see `docs/adr/0004-sqlite-reseed-on-render.md`).

**Tech Stack:** FastAPI + uvicorn (Docker on Render), Vite/React (Vercel), GitHub Actions, `gh` CLI for branch protection.

**Spec:** `docs/superpowers/specs/2026-09-25-cicd-render-vercel-design.md`

## Global Constraints

- Database stays SQLite for this pass — no Postgres/Supabase migration (spec decision 2).
- No new frontend test framework is introduced; frontend verification uses `tsc -b` / `oxlint` / build-output inspection, matching the project's current (test-less) frontend tooling.
- `.env` must never be committed; secrets (`GOOGLE_API_KEY`) are set directly in the Render/Vercel dashboards, never written into `render.yaml`/`vercel.json`/workflow files.
- Repo is `github.com/lamtd1/test`, default branch `main`.

---

### Task 1: Fix broken `requirement.txt` (blocks every install below)

**Files:**
- Modify: `requirement.txt:16-19`

**Interfaces:** none (dependency file only).

- [ ] **Step 1: Reproduce the failure**

Run: `python3 -m pip install --dry-run -r requirement.txt`
Expected: FAIL — `qlalchemy` (line 17) is not a real PyPI package (typo for `sqlalchemy`), so resolution errors out. This line has no ORM caller anywhere in `src/` (ADR 0001 chose no-ORM), so it's dead weight, not a real dependency to fix-forward.

- [ ] **Step 2: Comment out the unused Database block**

Change lines 16-19 from:
```
# Database (uncomment as needed)
qlalchemy>=2.0.0
alembic>=1.14.0
psycopg2-binary>=2.9.0
```
to:
```
# Database (uncomment as needed — not used yet, ADR 0001 keeps no-ORM SQLite)
# sqlalchemy>=2.0.0
# alembic>=1.14.0
# psycopg2-binary>=2.9.0
```

- [ ] **Step 3: Verify the install resolves**

Run: `python3 -m pip install --dry-run -r requirement.txt`
Expected: PASS (no resolution errors). If your local pip is too old for `--dry-run`, instead run the real install inside the project's `.venv`: `. .venv/bin/activate && pip install -r requirement.txt` and expect exit code 0.

- [ ] **Step 4: Commit**

```bash
git add requirement.txt
git commit -m "fix: comment out unused sqlalchemy typo blocking pip install

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: CORS origins from environment

**Files:**
- Modify: `src/config.py`
- Modify: `src/main.py:12-16`
- Test: `tests/test_config.py` (new)

**Interfaces:**
- Produces: `Settings.cors_origins: list[str]` (parsed from `CORS_ORIGINS` env, comma-separated, whitespace-stripped, defaults to `["http://localhost:5173", "http://127.0.0.1:5173"]` when unset/empty).
- Produces: `src.config.parse_cors_origins(raw: str | None) -> list[str]` (pure helper, testable in isolation).

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:
```python
"""CORS_ORIGINS env var parsing — xem docs/superpowers/specs/2026-09-25-cicd-render-vercel-design.md."""

from src.config import parse_cors_origins


def test_parse_cors_origins_defaults_when_unset():
    assert parse_cors_origins(None) == [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


def test_parse_cors_origins_defaults_when_empty():
    assert parse_cors_origins("") == [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


def test_parse_cors_origins_splits_and_strips():
    raw = "https://homematch.vercel.app, https://homematch-git-main.vercel.app"
    assert parse_cors_origins(raw) == [
        "https://homematch.vercel.app",
        "https://homematch-git-main.vercel.app",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_cors_origins'`

- [ ] **Step 3: Implement `parse_cors_origins` and wire it into `Settings`**

In `src/config.py`, add above the `Settings` class:
```python
_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def parse_cors_origins(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
```

Inside `Settings`, add a field for the raw env value and a computed property (pydantic-settings reads `CORS_ORIGINS` case-insensitively per existing `case_sensitive: False` config):
```python
    cors_origins_raw: str = Field(default="", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return parse_cors_origins(self.cors_origins_raw)
```
Place `cors_origins_raw` next to the other `Field(..., alias=...)` declarations (after `google_api_key`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire `Settings.cors_origins` into the FastAPI app**

In `src/main.py`, replace:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```
with:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
(`settings` is already defined a few lines above via `settings = get_settings()`.)

- [ ] **Step 6: Run the full test suite to confirm nothing else broke**

Run: `pytest -v`
Expected: PASS (all existing tests plus the 3 new ones)

- [ ] **Step 7: Commit**

```bash
git add src/config.py src/main.py tests/test_config.py
git commit -m "feat: read CORS allow-list from CORS_ORIGINS env var

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend API base URL from environment

**Files:**
- Modify: `web/src/lib/api.ts:1`
- Create: `web/.env.example`

**Interfaces:**
- Produces: `BASE` in `web/src/lib/api.ts` now resolves from `import.meta.env.VITE_API_URL`, falling back to `"http://localhost:8000/api/v1"`. No other exported symbol in this file changes.

- [ ] **Step 1: Change the hardcoded BASE**

In `web/src/lib/api.ts`, replace line 1:
```ts
const BASE = "http://localhost:8000/api/v1";
```
with:
```ts
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
```

- [ ] **Step 2: Document the env var for local/dev use**

Create `web/.env.example`:
```
# Copy to .env.local for local dev against a non-default backend.
# Vercel: set VITE_API_URL as a Project Environment Variable pointing at the Render URL,
# e.g. https://homematch-api.onrender.com/api/v1
VITE_API_URL=http://localhost:8000/api/v1
```

- [ ] **Step 3: Verify the default (unset) behavior still builds and points at localhost**

Run: `cd web && npm run build`
Expected: build succeeds; then run `grep -o 'http://localhost:8000/api/v1' dist/assets/*.js` and expect at least one match (confirms the fallback compiled in when `VITE_API_URL` is unset).

- [ ] **Step 4: Verify an override actually takes effect**

Run: `cd web && VITE_API_URL=https://example-test.onrender.com/api/v1 npm run build`
Expected: build succeeds; `grep -o 'https://example-test.onrender.com/api/v1' dist/assets/*.js` matches, and `grep -o 'http://localhost:8000/api/v1' dist/assets/*.js` does NOT match (confirms the env var, not the fallback, was compiled in).

- [ ] **Step 5: Run type-check and lint**

Run: `cd web && npx tsc -b && npm run lint`
Expected: both PASS with no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/api.ts web/.env.example
git commit -m "feat: read API base URL from VITE_API_URL env var

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Dockerfile (reseed-on-boot backend image)

**Files:**
- Modify: `Dockerfile` (currently empty)

**Interfaces:**
- Produces: a Docker image that, on `docker run`, seeds SQLite from `data/*.csv` and then serves the FastAPI app on `$PORT` (defaults to 8000).

- [ ] **Step 1: Write the Dockerfile**

Replace the (empty) contents of `Dockerfile` with:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

COPY . .

ENV PYTHONPATH=/app
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "python scripts/seed.py && uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Build the image**

Run: `docker build -t homematch-api .`
Expected: build completes with exit code 0 (this also re-verifies Task 1's `requirement.txt` fix inside a clean container, independent of your local venv).

- [ ] **Step 3: Run it and confirm the reseed + health check**

Run:
```bash
docker run --rm -d -p 8000:8000 --name homematch-test homematch-api
sleep 3
curl -sf http://localhost:8000/api/v1/health
docker logs homematch-test
docker stop homematch-test
```
Expected: `curl` prints `{"status":"ok","env":"development"}`; `docker logs` shows the `Seeded N projects, ...` line from `scripts/seed.py` before uvicorn's startup log.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "feat: build backend Docker image that reseeds SQLite on boot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `render.yaml` Blueprint

**Files:**
- Create: `render.yaml`

**Interfaces:** none (Render reads this file directly when you import the repo as a Blueprint).

- [ ] **Step 1: Write render.yaml**

```yaml
services:
  - type: web
    name: homematch-api
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerContext: .
    plan: free
    envVars:
      - key: GOOGLE_API_KEY
        sync: false
      - key: LLM_PROVIDER
        value: gemini
      - key: CORS_ORIGINS
        sync: false
      - key: APP_ENV
        value: production
```
(`sync: false` marks a secret Render will prompt for in the dashboard instead of storing in git; `CORS_ORIGINS` is `sync: false` because its value — the Vercel URL — doesn't exist until Task 6/7's Vercel import happens.)

- [ ] **Step 2: Validate the YAML parses**

Run: `python3 -c "import yaml; print(yaml.safe_load(open('render.yaml')))"`
Expected: prints the parsed dict with no exception. (If `pyyaml` isn't installed locally, run `pip install pyyaml` first — it's a one-off validation tool, not a project dependency, so don't add it to `requirement.txt`.)

- [ ] **Step 3: Commit**

```bash
git add render.yaml
git commit -m "feat: add Render Blueprint for backend deploy

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: GitHub Actions CI gate

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:** none (workflow file; job names `backend` and `frontend` are referenced by Task 8's branch protection setup).

- [ ] **Step 1: Write the workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirement.txt
      - run: ruff check .
      - run: pytest -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npx tsc -b
      - run: npm run lint
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python3 -c "import yaml; print(yaml.safe_load(open('.github/workflows/ci.yml')))"`
Expected: prints the parsed dict with no exception.

- [ ] **Step 3: Commit and push, then confirm on GitHub**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint + test gate for backend and frontend

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push origin main
```
Then open `https://github.com/lamtd1/test/actions` and confirm a "CI" run started for this push and both the `backend` and `frontend` jobs finish green (they should, since Tasks 1-4 already fixed the install and the frontend build/lint).

---

### Task 7: ADR — SQLite reseed-on-boot vs. Supabase migration

**Files:**
- Create: `docs/adr/0004-sqlite-reseed-on-render.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Write the ADR**

Match the existing format used by `docs/adr/0001-sqlite-for-prototype.md` (Trạng thái / Bối cảnh / Quyết định / Vì sao / Đánh đổi):

```markdown
# 0004: SQLite reseed-on-boot thay vì migrate Supabase ngay

Trạng thái: Đã chấp nhận (2026-09-25)

## Bối cảnh

Deploy backend lên Render. Render (free tier) xoá filesystem mỗi lần
redeploy/restart, nên file SQLite (`data/app.db`) không sống sót qua các
lần deploy. Hai hướng: (a) migrate sang Supabase (Postgres managed, có
sẵn từ đầu trong `docs/schemas.md`), hoặc (b) giữ SQLite và reseed lại
từ `data/*.csv` mỗi lần container khởi động.

## Quyết định

Giữ SQLite, reseed lại toàn bộ DB từ `data/*.csv` mỗi lần container boot
(`scripts/seed.py` chạy trước `uvicorn` trong Dockerfile CMD — xem
docs/superpowers/specs/2026-09-25-cicd-render-vercel-design.md).

## Vì sao

- `docs/schemas.md` vốn viết cho Postgres nên việc migrate sau này (khi
  cần) không mất công viết lại schema, chỉ cần đổi driver + kiểm lại
  CHECK constraint trên Postgres — hoãn lại không tốn chi phí kỹ thuật.
- Đây vẫn là prototype phục vụ demo/happy-case, không có dữ liệu người
  dùng thật cần giữ lại giữa các lần deploy.
- Không cần trả phí Render persistent disk hay set up Supabase project
  ngay khi chưa cần độ bền dữ liệu.

## Đánh đổi

- Mọi session/shortlist/audit_log tạo ra giữa 2 lần deploy sẽ mất khi
  redeploy — chấp nhận được cho giai đoạn demo, không chấp nhận được
  nếu có buổi demo trực tiếp với sale/khách hàng thật kéo dài và deploy
  giữa chừng.
- Khi cần nhiều instance/scale ngang, SQLite (một file, một tiến trình)
  sẽ không còn phù hợp — lúc đó bắt buộc phải migrate Postgres/Supabase.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0004-sqlite-reseed-on-render.md
git commit -m "docs: add ADR 0004 for SQLite reseed-on-boot vs Supabase

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: README deploy section + branch protection

**Files:**
- Modify: `README.md` (append a new `## Deploy (Render + Vercel)` section, e.g. after the existing `## Environment Variables` section at line 84)

**Interfaces:** none (documentation + one repo-settings API call).

- [ ] **Step 1: Add the README section**

Insert after the `## Environment Variables` section:
```markdown
## Deploy (Render + Vercel)

Push-to-deploy is wired via each platform's native GitHub integration —
GitHub Actions only runs the CI gate (`.github/workflows/ci.yml`), it does
not perform the deploys itself.

**Backend (Render), one-time setup:**
1. Render dashboard → New → Blueprint → connect `lamtd1/test`. Render reads
   `render.yaml` and creates the `homematch-api` web service automatically.
2. In the service's Environment tab, set the secrets marked `sync: false`
   in `render.yaml`: `GOOGLE_API_KEY` (your Gemini key) and `CORS_ORIGINS`
   (leave blank until Vercel gives you a URL in step 2 below, then come
   back and fill it in, comma-separated if you have both a production and
   a preview domain).
3. Every push to `main` redeploys automatically; the container reseeds
   SQLite from `data/*.csv` on every boot (see
   `docs/adr/0004-sqlite-reseed-on-render.md`), so demo data is always
   fresh, not persisted between deploys.

**Frontend (Vercel), one-time setup:**
1. Vercel dashboard → Add New → Project → import `lamtd1/test`, set Root
   Directory to `web`. Vercel auto-detects the Vite build.
2. Project → Settings → Environment Variables → add `VITE_API_URL` =
   `https://<your-render-service>.onrender.com/api/v1`.
3. Every push to `main` deploys to production; every PR gets a preview
   URL automatically.
4. Copy the resulting Vercel production URL back into Render's
   `CORS_ORIGINS` env var (step 2 above) so the backend accepts requests
   from it.
```

- [ ] **Step 2: Set up branch protection so the CI gate is mandatory**

Run (requires `gh` CLI already authenticated as `lamtd1`):
```bash
gh api repos/lamtd1/test/branches/main/protection \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=backend" \
  -f "required_status_checks[contexts][]=frontend" \
  -F "enforce_admins=true" \
  -F "required_pull_request_reviews=null" \
  -F "restrictions=null"
```
Expected: prints the updated branch protection JSON with `"contexts": ["backend", "frontend"]`.

- [ ] **Step 3: Verify**

Run: `gh api repos/lamtd1/test/branches/main/protection --jq '.required_status_checks.contexts'`
Expected: `["backend", "frontend"]`

- [ ] **Step 4: Commit the README change**

```bash
git add README.md
git commit -m "docs: document Render/Vercel deploy setup steps

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push origin main
```

---

## After this plan

Manual, one-time dashboard steps the user still has to do themselves
(cannot be scripted from here without their Render/Vercel/GitHub OAuth):
importing the Render Blueprint, importing the Vercel project, and pasting
in the two secrets (`GOOGLE_API_KEY`, `CORS_ORIGINS`). README Task 8
documents the exact clicks.
