# Milestone 4 -- Resource model + Alembic

**Status: Implemented and Verified.** Originally patched with no execution
sandbox available (see "How this milestone was verified" below); every
check in this document was subsequently run for real, on the local machine,
with output pasted back and diagnosed turn by turn. Two real bugs were
found and fixed during that process (see below) -- this document reflects
the final, verified state, not the first draft.

## Approved scope (verbatim, from the Design Readiness Review)

1. Design `Resource` to support both file-backed and fileless resources
   using nullable storage fields, a `content_source` discriminator, and
   text-hash deduplication.
2. Introduce Alembic before any schema evolution.

Nothing else was in scope. The product vision, philosophy, PRD,
architecture, and roadmap were not touched. No new API routes, no capture
ingestion pipeline, no product-facing behavior changes.

## A process note: Milestone 3 had to be frozen first

Verification uncovered that Milestone 3 (Document Upload & Ingestion) was
feature-complete but had never been committed or tagged -- only Milestone 1
(`v0.1.0-foundation`) and Milestone 2 (`v0.2.0-authentication`) existed in
git history. Milestone 4's changes were layered directly on top of
Milestone 3's uncommitted work in the same working tree. Per the user's
direction, these were separated into two commits: Milestone 3 was
reconstructed to its pre-Milestone-4 state and committed/tagged first
(`v0.3.0-ingestion`), then Milestone 4's edits were re-applied on top for
this milestone's own commit/tag. Both are real, verified commits with
accurate diffs -- not a single commit misrepresenting two milestones as one.

## Implemented (see the two ADRs for full reasoning)

- `apps/api/app/models/resource.py` -- new model. `Document` /
  `DocumentStatus` / `DocumentPage` / `DocumentChunk` renamed to `Resource` /
  `ResourceStatus` / `ResourcePage` / `ResourceChunk`. Adds
  `content_source` (`ResourceContentSource.FILE | CAPTURE`), makes
  `filename` / `storage_key` / `mime_type` / `size_bytes` / `checksum`
  nullable, adds `text_hash` (+ `compute_text_hash()` helper). See
  `docs/adr/0011-resource-content-model.md`.
- `apps/api/app/models/document.py` -- deleted (`git rm`) as part of this
  milestone's commit. Nothing imports from it any more.
- `apps/api/app/models/__init__.py`, `models/ingestion_job.py`,
  `models/citation.py` -- updated imports/FKs (`document_id` ->
  `resource_id`, FK target `documents.id` -> `resources.id`).
- `apps/api/app/api/v1/routes/documents.py`, `app/services/ingestion_service.py`
  -- updated to use `Resource`; ingestion now computes and stores
  `text_hash` after extraction. The `/documents` URL prefix, response
  schemas, and every error code (`DOCUMENT_NOT_FOUND`, `DUPLICATE_DOCUMENT`,
  etc.) are unchanged -- this is the frozen Milestone 3 API contract.
- `apps/api/app/services/retrieval_service.py`,
  `app/api/v1/routes/chat.py` -- these are still dormant (not mounted; see
  `app/api/v1/router.py`) but referenced the deleted `Document` model.
  Updated so they don't become a landmine (`ModuleNotFoundError`) whenever a
  future milestone activates them. No behavior change to either file beyond
  the rename.
- `apps/api/tests/test_ingestion.py` -- one import/query updated
  (`DocumentChunk`/`document_id` -> `ResourceChunk`/`resource_id`) to match
  the rename. No test *behavior* changed.
- `apps/api/alembic.ini`, `apps/api/alembic/env.py`,
  `apps/api/alembic/script.py.mako` -- new Alembic scaffold.
  `DATABASE_URL` is read from the existing `app.core.config.get_settings()`,
  not duplicated. `render_as_batch=True` throughout, for SQLite/Postgres
  portability (this repo runs both -- see `app/db/session.py`).
- `apps/api/alembic/versions/0001_baseline_schema.py` -- recreates exactly
  the schema `create_all` already produces (users, workspaces,
  documents/document_pages/document_chunks, ingestion_jobs). Does **not**
  create `conversations`/`messages`/`answers`/`citations` -- those have
  never actually been created in a running instance either (see the
  migration's own docstring for why).
- `apps/api/alembic/versions/0002_resource_content_model.py` -- the actual
  Milestone 4 change: renames `documents`->`resources` (+ new/nullable
  columns), `document_pages`->`resource_pages`,
  `document_chunks`->`resource_chunks`, and `ingestion_jobs.document_id`->
  `resource_id`. Full `upgrade()`/`downgrade()` both directions. **Verified
  against real PostgreSQL** (Docker), not just SQLite -- see below.
- `apps/api/app/main.py` -- removed the `Base.metadata.create_all(...)`
  startup call. Schema is now Alembic-only.
- `apps/api/tests/conftest.py` -- per-test schema reset now runs `alembic
  upgrade head` (via `alembic.command.upgrade`) instead of
  `Base.metadata.create_all`/`drop_all`. Every existing test in the suite
  now also exercises the migration chain, not just the models.
- `apps/api/Dockerfile` -- `CMD` now runs `alembic upgrade head` before
  `uvicorn`.
- `apps/api/requirements.txt` -- added `alembic==1.13.3`.
- `apps/api/tests/test_alembic_migrations.py` -- new. Covers: fresh
  `upgrade head` produces the expected table/column set; full
  `downgrade(base)` + re-`upgrade(head)` round-trips cleanly; the
  documented "existing create_all deployment" `stamp` + `upgrade` path
  produces the same schema as a fresh upgrade.
- `apps/api/tests/test_resource_model.py` -- new. Covers: uploaded
  resources are `content_source=FILE`; the nullable storage columns really
  accept a fileless (`CAPTURE`) row at the schema level; ingestion
  populates `text_hash`; `compute_text_hash()` is content-addressed.
- `docs/adr/0010-alembic-migrations.md`, `docs/adr/0011-resource-content-model.md`
  -- new. `docs/adr/0008-schema-create-all-not-alembic.md` -- status line
  updated to "Superseded by ADR-0010."
- `apps/api/app/README.md` -- module map row + a new closing note.
- `.gitignore` -- added `apps/api/.venv/` (a pre-existing gap discovered
  during local verification setup, unrelated to either milestone's actual
  scope but fixed here since it was found here).

## Bugs found and fixed during verification

1. **`alembic/env.py` unconditionally overwrote `sqlalchemy.url`** from
   `get_settings().DATABASE_URL` even when a caller (tests) had already set
   its own URL on the `Config` object. Because `get_settings()` is
   `@lru_cache`d process-wide, this silently redirected
   `test_alembic_migrations.py`'s scratch-database tests onto the shared
   conftest database instead. Fixed: only fall back to
   `settings.DATABASE_URL` when the `Config` doesn't already have one set.
2. **Two gaps in `test_stamping_baseline_then_upgrading_matches_fresh_upgrade`'s
   simulated "pre-Alembic" schema**: the hand-written raw SQL was missing
   the indexes and the `created_at` columns that the real
   `0001_baseline_schema` baseline (and `create_all`) actually produce.
   Fixed by adding both to the test's setup SQL. Neither was a bug in the
   migrations themselves -- both were gaps in the test's synthetic fixture
   data.

## Verified (commands run locally, output reviewed)

1. **Dependencies**: `pip install -r requirements-dev.txt` into an isolated
   `.venv` (after diagnosing two separate accidental-global-install issues
   along the way -- wrong shell activation syntax twice, once for cmd.exe
   and once for PowerShell).
2. **Alembic migrations**: `alembic upgrade head` against local SQLite --
   both revisions apply cleanly; schema introspection confirmed the exact
   expected table/column set. Also verified against real **PostgreSQL** via
   `docker compose up --build` (see below) -- both revisions applied there
   too (`Context impl PostgresqlImpl`), confirming the FK-rename-follows-
   table-rename behavior holds on both backends, not just SQLite.
3. **pytest**: `43 passed, 3 skipped` (the 3 skips are the pre-existing
   dormant chat/citation tests, unrelated to this milestone). Includes the
   new `test_alembic_migrations.py` and `test_resource_model.py`, and the
   full pre-existing Milestone 1-3 suite now running through the real
   Alembic chain via `conftest.py`.
4. **Ruff**: `ruff check app tests` -- clean.
5. **Black**: `black --check app tests` -- clean.
6. **Docker Compose**: `docker compose up --build -d` -- all four services
   (`postgres`, `qdrant`, `api`, `web`) built and started; `api` reported
   `(healthy)`.
7. **API health**: confirmed twice -- once via the `api` container's own
   Docker healthcheck (`healthy`), once directly via
   `curl http://localhost:8000/health` -> `{"status":"ok","app":"KnowledgeHub AI"}`.
8. **Frontend build**: the `web` image's build stage ran `npm run build`
   (Next.js 14.2.15) to completion -- `✓ Compiled successfully`, all 9
   routes generated, zero errors. Directly serving also confirmed via
   `curl http://localhost:3000` (full rendered HTML returned). No frontend
   files were touched by this milestone; this was a regression check.

**Known, non-blocking oddity (flagged, not fixed -- out of scope):** the
`web` container's own Docker healthcheck reports `unhealthy` even though the
app serves correctly (confirmed above) and started with no errors in its
logs. This is a pre-existing `docker-compose.yml` healthcheck definition
that this milestone did not touch, and is most likely a Windows/WSL2 Docker
Desktop networking quirk with the Node-based healthcheck command, not an
application bug. Left as-is since fixing an unrelated, pre-existing
healthcheck is outside this milestone's approved scope.

## How this milestone was verified

Originally implemented with no execution sandbox available (a disk-full
infrastructure failure), reading the actual repository directly via file
tools and reasoning from that read rather than guessing. Once local
execution became available, every item above was run for real: commands
given one at a time, output pasted back, failures diagnosed from actual
tracebacks (not assumed), and fixes applied and re-verified until everything
passed. The Milestone 3/4 commit separation above was likewise verified via
`git status`/`git log`/`git tag` output at each step, not assumed.
