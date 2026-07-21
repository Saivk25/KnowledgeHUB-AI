# KnowledgeHub AI

**Your Organization's Intelligence, Instantly Searchable.**

> **Status: Milestone 2 -- Authentication & Workspace.** This README
> describes only what exists right now. Document ingestion and RAG chat
> are specified in the frozen SRS and will be built in the milestones
> that follow, each reviewed and approved before the next begins. See
> [Roadmap](#roadmap) below.

## What this milestone proves

Real accounts, real sessions, real isolation. A user can register, log
in, and land in a private workspace that belongs only to them --
enforced server-side, not just hidden in the UI -- on top of the
Milestone 1 foundation (Next.js + FastAPI + PostgreSQL + Qdrant, all
containerized and health-checked).

## What's included

- Monorepo layout (`apps/api`, `apps/web`)
- FastAPI backend: CORS (`GET`/`POST`/`PATCH`, credentials enabled for the
  session cookie -- see Security below), structured logging, generic
  error handling (including request-validation errors -- see Security),
  liveness (`GET /health`) and readiness (`GET /health/ready`) endpoints
- Authentication: register, login, logout, `GET /api/v1/auth/me`; bcrypt
  password hashing; JWT sessions delivered as an httpOnly cookie (browser
  clients) and also returned in the response body (non-browser clients),
  either of which `app/deps.get_current_user` will accept
- Workspace: every account gets a personal workspace on registration
  (`GET`/`PATCH /api/v1/workspace`); user profile updates
  (`PATCH /api/v1/users/me`); a minimal workspace shell screen after login;
  `workspaces.owner_user_id` is indexed since every protected request
  looks up "the current user's workspace" by that column
- All authenticated response shapes (`/auth/me`, `/workspace`, `/users/me`)
  have explicit Pydantic `response_model`s, so the OpenAPI schema at
  `/docs` matches what the endpoints actually return
- Next.js frontend: landing page with Login/Register CTAs and a live
  system-status panel, login/register/settings screens, a protected
  workspace shell (`AuthProvider` + `useRequireAuth` redirect unauthenticated
  visitors to `/login`)
- PostgreSQL (via SQLAlchemy) and Qdrant, both reachability-checked by
  `/health/ready`; `users` and `workspaces` tables now exist
- Docker Compose stack: `postgres`, `qdrant`, `api`, `web`. `api` and `web`
  build lean, dependency-minimal images (see Security below); each has a
  container health check except `qdrant` (see the comment in
  `docker-compose.yml` for why)
- CI: backend lint (`ruff` + `black --check`), backend tests (`pytest`),
  frontend type-check (`tsc --noEmit`) + build

## What's deliberately not included yet

No document upload, no embeddings, no RAG. Screens and backend modules
for those features were prototyped in an earlier pass and still exist in
the repository (see [Roadmap](#roadmap),
[`apps/api/app/README.md`](apps/api/app/README.md), and
[`apps/web/app/_future/README.md`](apps/web/app/_future/README.md)), but
they are **not wired into the running application** -- `app/api/v1/router.py`
mounts only `auth` and `workspace`, and the corresponding Next.js pages
(`documents/`, `chat/`) sit in a Next.js "private folder" (`app/_future/`)
so they are not routable. `GET /workspace` also does not yet report
document counts, for the same reason (see that module's docstring). This
is intentional: each feature goes live only in the milestone that
introduces it, after review.

## Security posture for this milestone

- CORS allows exactly one origin (`WEB_ORIGIN`, default
  `http://localhost:3000`), `GET`/`POST`/`PATCH` only, and
  `allow_credentials=True` -- required now that the session is carried in
  a cookie. Still never a wildcard origin.
- Passwords are hashed with bcrypt (`passlib`), never stored or logged in
  plaintext, and never echoed back in a response -- including on a
  validation failure. (FastAPI's default handler for invalid request
  bodies echoes the raw submitted value for every invalid field; a custom
  `RequestValidationError` handler in `app/main.py` replaces that with the
  same `{"error": {code, message, requestId}}` envelope used everywhere
  else, listing only the field path and message, never the value.)
- The session cookie is `httponly` (JavaScript cannot read it),
  `samesite=lax` (not sent on cross-site requests), and `secure` whenever
  `ENV=production` (see `.env.example` and
  `apps/api/app/api/v1/routes/auth.py`) -- off for local `http://localhost`
  development, on for any real deployment.
- Login and "unknown email" both return the same 401
  `INVALID_CREDENTIALS` response so the endpoint never reveals which
  emails have accounts. Duplicate registration returns 409 `EMAIL_TAKEN`.
- `GET`/`PATCH /workspace` and `PATCH /users/me` resolve "whose workspace"
  strictly from the authenticated session (no id path parameter exists),
  so one account can never read or modify another account's workspace.
- **Known, accepted limitation (ADR-0001):** logout clears the session
  cookie, ending the browser session immediately, but the underlying JWT
  is stateless and not server-side revoked -- a copy of the token obtained
  from a register/login response body (non-browser clients) remains
  cryptographically valid until its 24h expiry even after logout.
  Immediate revocation ("log out everywhere") requires a session store,
  which ADR-0001 explicitly defers past the MVP; this is a frozen
  trade-off, not an oversight.
- No secrets are hardcoded. `docker-compose.yml` uses an obviously-labeled
  local dev database password (`knowledgehub`/`knowledgehub`, local network
  only); `app/core/config.py`'s `JWT_SECRET` default is named
  `dev-secret-change-me` specifically so it cannot be mistaken for a real
  secret -- set a real one via the `JWT_SECRET` environment variable (and
  `ENV=production`) for anything beyond local development.
- No debug flags are enabled: no `--reload` in either Dockerfile's `CMD`,
  no FastAPI debug mode.
- Both runtime images install only Milestone 1 + Milestone 2 dependencies:
  the API image installs `requirements.txt` only (no
  `pytest`/`ruff`/`black`/`PyMuPDF`; the `httpx` present in a `pip list` is
  a transitive runtime dependency of `qdrant-client`, not the standalone
  package deferred for the AI-provider milestone); the web image is built
  with Next.js `output: "standalone"` so the runtime layer excludes
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

No `.env` file is required to run the Docker Compose stack locally.

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
   landing page loads with Login/Register CTAs and the "Live system
   status" panel shows API, Database, and Vector DB all **Up** within a
   few seconds.
2. Click "Sign up", register a new account. You land on `/workspace`
   signed in, seeing your own workspace name.
3. Log out, then log back in with the same credentials -- you land on
   `/workspace` again.
4. Try registering a second account with the same email -- returns 409
   `EMAIL_TAKEN`. Try logging in with a wrong password, or an email that
   was never registered -- both return the same 401
   `INVALID_CREDENTIALS` (the API never reveals which emails exist).
5. Try registering with a password under 8 characters -- returns 422 with
   a `VALIDATION_ERROR` body that names the `password` field but never
   echoes the submitted value.
6. Visit `/settings`, change your display name and workspace name, save,
   then reload -- both changes persisted.
7. Open a private/incognito window and visit `/workspace` directly
   without logging in -- you're redirected to `/login`, confirming the
   route is actually protected server-side, not just hidden in the UI.
8. Register two different accounts (e.g. in two browser profiles) and
   confirm each sees only their own workspace name -- never the other
   account's.
9. `curl http://localhost:8000/health` returns `{"status":"ok","app":"KnowledgeHub AI"}`.
10. `curl -i http://localhost:8000/health/ready` returns HTTP 200 with
    `"status":"ready"` and both components `"up"` while the stack is
    running.
11. `docker compose stop qdrant`, then re-run the readiness check: it now
    returns HTTP 503 with `"status":"degraded"` and
    `"vector_db":{"status":"down"}`, while `database` still reports `"up"`.
    `docker compose start qdrant` to restore it.
12. Visiting a not-yet-built route (e.g. http://localhost:3000/documents
    or http://localhost:8000/api/v1/documents) returns a 404 -- confirming
    Milestone 3/4 features are not silently half-available.
13. `curl -i -H "Origin: http://evil.example" http://localhost:8000/health`
    -- the response should not include an
    `Access-Control-Allow-Origin: http://evil.example` header, confirming
    CORS is restricted to `WEB_ORIGIN`.

## Testing

```bash
cd apps/api
pip install -r requirements-dev.txt
pytest -q      # 22 passed, 2 skipped (deferred to Milestone 3)
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
  documents the overrides available for running services outside Docker,
  including `JWT_SECRET` and `ENV` (introduced this milestone).
- `app/core/config.py` declares settings fields for later milestones
  (storage, embedding/LLM provider) with safe, clearly-fake defaults.
  This is deliberate -- see `apps/api/app/README.md` -- and none of those
  fields are read by any code path that runs in Milestone 1 or 2.
- `GET /workspace` intentionally omits document counts (`stats`) until
  Milestone 3 introduces the `Document` model -- see that route's
  docstring in `apps/api/app/api/v1/routes/workspace.py`.
- Logout does not server-side revoke the JWT (see Security above); this is
  an accepted MVP trade-off per ADR-0001, not a gap to close in this
  milestone.
- Schema changes still use `Base.metadata.create_all` rather than Alembic
  migrations (see `docs/adr/0008`); acceptable while there's no production
  data yet to migrate around.

## Repository layout

```
knowledgehub-ai/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── README.md                 # module -> milestone map
│   │   │   ├── api/routes/health.py       # Milestone 1 -- live
│   │   │   ├── api/v1/routes/auth.py      # Milestone 2 -- live
│   │   │   ├── api/v1/routes/workspace.py # Milestone 2 -- live
│   │   │   ├── api/v1/routes/documents.py, chat.py  # Milestones 3-4 -- not mounted
│   │   │   ├── core/, db/, models/, services/, schemas/
│   │   │   └── main.py
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── page.tsx, layout.tsx       # Milestone 1 -- live
│       │   ├── login/, register/, workspace/, settings/  # Milestone 2 -- live
│       │   └── _future/documents/, _future/chat/          # Milestones 3-4 -- not routed
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
| 1 | Project foundation: monorepo, Docker Compose, Postgres, Qdrant, health checks | Frozen (`v0.1.0-foundation`) |
| 2 | Authentication + workspace | **Current** |
| 3 | Document upload + ingestion pipeline | Not started |
| 4 | RAG chat with page-level citations | Not started |
| 5 | Source Viewer + UX polish | Not started |
| 6 | Portfolio release: seed data, docs, demo | Not started |

Detailed architecture decisions for the whole system (already reviewed and
frozen in the SRS) live in [`docs/adr/`](docs/adr/) -- they describe where
the project is going even though most of that code isn't wired in yet.

## License

MIT -- see [LICENSE](LICENSE).
