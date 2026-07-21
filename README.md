# KnowledgeHub AI

**Your Organization's Intelligence, Instantly Searchable.**

> **Status: Milestone 1 -- Project Foundation.** This README describes only
> what exists right now. Authentication, document ingestion, and RAG chat
> are specified in the frozen SRS and will be built in the milestones that
> follow, each reviewed and approved before the next begins. See
> [Roadmap](#roadmap) below.

## What this milestone proves

A clean, production-shaped foundation: a Next.js frontend and a FastAPI
backend, both containerized, talking to a real PostgreSQL database and a
real Qdrant vector database, with health checks that prove the wiring
works end to end -- before any business feature is built on top of it.

## What's included

- Monorepo layout (`apps/api`, `apps/web`)
- FastAPI backend: CORS (GET-only, no credentials -- see Security below),
  structured logging, generic error handling, liveness (`GET /health`) and
  readiness (`GET /health/ready`) endpoints
- Next.js frontend: app shell + a landing page with a live system-status
  panel that calls the API's health endpoints directly from the browser
- PostgreSQL (via SQLAlchemy) and Qdrant, both reachability-checked by
  `/health/ready`
- Docker Compose stack: `postgres`, `qdrant`, `api`, `web`. `api` and `web`
  build lean, dependency-minimal images (see Security below); each has a
  container health check except `qdrant` (see the comment in
  `docker-compose.yml` for why)
- CI: backend lint (`ruff` + `black --check`), backend tests (`pytest`),
  frontend type-check (`tsc --noEmit`) + build

## What's deliberately not included yet

No authentication, no document upload, no embeddings, no RAG. Screens and
backend modules for those features were prototyped in an earlier pass and
still exist in the repository (see [Roadmap](#roadmap),
[`apps/api/app/README.md`](apps/api/app/README.md), and
[`apps/web/app/_future/README.md`](apps/web/app/_future/README.md)), but
they are **not wired into the running application** -- `app/main.py`
mounts only the health router, and the corresponding Next.js pages sit in
a Next.js "private folder" (`app/_future/`) so they are not routable. This
is intentional: each feature goes live only in the milestone that
introduces it, after review.

## Security posture for this milestone

- CORS allows exactly one origin (`WEB_ORIGIN`, default
  `http://localhost:3000`), `GET` only, and `allow_credentials=False` --
  there are no cookies to send yet. This is re-opened deliberately in
  Milestone 2 alongside the feature that needs it, not before.
- No secrets are hardcoded. `docker-compose.yml` uses an obviously-labeled
  local dev database password (`knowledgehub`/`knowledgehub`, local network
  only); `app/core/config.py`'s `JWT_SECRET` default is named
  `dev-secret-change-me` specifically so it cannot be mistaken for a real
  secret, and it is not read by any code path in this milestone.
- No debug flags are enabled: no `--reload` in either Dockerfile's `CMD`,
  no FastAPI debug mode.
- Both runtime images install only Milestone 1 dependencies: the API image
  installs `requirements.txt` only (no `pytest`/`ruff`/`black`/`httpx`, no
  OS packages for not-yet-installed future dependencies); the web image is
  built with Next.js `output: "standalone"` so the runtime layer excludes
  `devDependencies` entirely (~23MB vs. ~285MB for a full `node_modules`).

## Running it locally

### Docker Compose (recommended)

```bash
cd knowledgehub-ai
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/health/ready

No `.env` file or API key is required for this milestone.

### Running services individually

```bash
# Backend
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# Falls back to SQLite automatically if DATABASE_URL is unset -- see
# app/core/config.py. Qdrant reachability will show as "down" in
# /health/ready unless a Qdrant instance is actually running.

# Frontend (separate terminal)
cd apps/web
npm install
npm run dev
```

## Manual test cases

1. `docker compose up --build`, then open http://localhost:3000. The
   landing page loads and the "Live system status" panel shows API,
   Database, and Vector DB all **Up** within a few seconds.
2. `curl http://localhost:8000/health` returns `{"status":"ok","app":"KnowledgeHub AI"}`.
3. `curl -i http://localhost:8000/health/ready` returns HTTP 200 with
   `"status":"ready"` and both components `"up"` while the stack is
   running.
4. `docker compose stop qdrant`, then re-run the readiness check: it now
   returns HTTP 503 with `"status":"degraded"` and
   `"vector_db":{"status":"down"}`, while `database` still reports `"up"`.
   `docker compose start qdrant` to restore it.
5. Visiting any not-yet-built route (e.g. http://localhost:3000/login or
   http://localhost:8000/api/v1/auth/register) returns a 404 -- confirming
   those features are not silently half-available.
6. `curl -i -H "Origin: http://evil.example" http://localhost:8000/health`
   -- the response should not include an
   `Access-Control-Allow-Origin: http://evil.example` header, confirming
   CORS is restricted to `WEB_ORIGIN`.

## Testing

```bash
cd apps/api
pip install -r requirements-dev.txt
pytest -q      # 4 passed, 7 skipped (deferred to their milestone)
ruff check app tests
black --check app tests
```

```bash
cd apps/web
npm install
npx tsc --noEmit
npm run build
```

## Assumptions

- PostgreSQL and Qdrant are treated as hard dependencies (readiness fails
  without them); there is no in-memory fallback in this milestone, unlike
  in the earlier prototype.
- The health check for the Qdrant container itself is intentionally
  omitted from `docker-compose.yml` because its base image does not
  reliably provide a shell utility to probe it with; the API's own
  `/health/ready` is the authoritative check instead (see the comment in
  `docker-compose.yml`).
- No `.env` values are required to run `docker compose up`; `.env.example`
  documents the overrides available for running services outside Docker.
- `app/core/config.py` declares settings fields for later milestones
  (JWT, storage, embedding/LLM provider) with safe, clearly-fake defaults.
  This is deliberate -- see `apps/api/app/README.md` -- and none of those
  fields are read by any code path that runs in Milestone 1.

## Repository layout

```
knowledgehub-ai/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── README.md                 # module -> milestone map
│   │   │   ├── api/routes/health.py       # Milestone 1 -- live
│   │   │   ├── api/v1/routes/             # future milestones -- not mounted
│   │   │   ├── core/, db/, models/, services/, schemas/
│   │   │   └── main.py
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── page.tsx, layout.tsx       # Milestone 1 -- live
│       │   └── _future/                   # future milestones -- not routed
│       ├── components/, lib/
├── docs/
│   ├── adr/            # architecture decision records
│   └── architecture/
├── demo-data/           # sample PDFs prepared for the ingestion milestone
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Roadmap

| Milestone | Scope | Status |
|---|---|---|
| 1 | Project foundation: monorepo, Docker Compose, Postgres, Qdrant, health checks | **Current -- frozen** |
| 2 | Authentication + workspace | Not started |
| 3 | Document upload + ingestion pipeline | Not started |
| 4 | RAG chat with page-level citations | Not started |
| 5 | Source Viewer + UX polish | Not started |
| 6 | Portfolio release: seed data, docs, demo | Not started |

Detailed architecture decisions for the whole system (already reviewed and
frozen in the SRS) live in [`docs/adr/`](docs/adr/) -- they describe where
the project is going even though most of that code isn't wired in yet.

## License

MIT -- see [LICENSE](LICENSE).
