# ADR-0010: Alembic-managed migrations, replacing `create_all`

**Status:** Accepted (Milestone 4)

**Supersedes:** ADR-0008 (`Base.metadata.create_all` instead of Alembic).

**Decision:** Schema changes are applied via Alembic migrations
(`apps/api/alembic/versions/`). `Base.metadata.create_all` no longer runs
anywhere in the application (the call in `app/main.py`'s startup handler was
removed). `alembic upgrade head` runs once, out of band, before the API
starts in every environment: `apps/api/Dockerfile`'s `CMD` for
Docker/production, `apps/api/tests/conftest.py`'s autouse fixture for tests,
and manually (or via a setup script) for local non-Docker development.

**Why now:** ADR-0008 explicitly scoped its own reversal: *"Revisit when the
schema needs to evolve against data that must be preserved — the first
Phase 2 milestone that touches the database should introduce Alembic at
that point, not before."* Milestone 4 is that milestone: it renames
`documents` to `resources` (see ADR-0011) against a schema that, in any real
deployment, already holds Milestone 1-3 data. `create_all` has no concept of
"rename a table" or "alter a column's nullability" -- it only ever adds
tables/columns that don't exist yet. Continuing without Alembic here would
mean hand-writing one-off SQL against production, unreviewed and
untracked -- exactly what ADR-0008 named as the trigger to stop doing this.

**Migration chain structure:** two revisions, deliberately kept separate:

- `0001_baseline_schema`: recreates exactly the schema `create_all` already
  produces today (users, workspaces, documents/document_pages/
  document_chunks, ingestion_jobs) -- nothing new. This exists so
  Alembic has a revision 0 to attach real changes to, and so a fresh
  database (new dev machine, CI, empty Docker volume) can reach the same
  schema as an existing deployment purely by running migrations.
- `0002_resource_content_model`: the actual Milestone 4 change (see
  ADR-0011).

**Existing (pre-Alembic) deployments:** must run `alembic stamp
0001_baseline_schema` before `alembic upgrade head`, so Alembic marks that
revision as already applied instead of re-running its `CREATE TABLE`
statements against tables that already exist. This is documented in
`0001_baseline_schema.py`'s own docstring and covered by
`tests/test_alembic_migrations.py::test_stamping_baseline_then_upgrading_matches_fresh_upgrade`.
Fresh databases just run `alembic upgrade head` with no stamping step.

**Why not run migrations inside the app process at startup:** `create_all`
was safe to call on every boot because it is idempotent and side-effect-free
against an already-correct schema. A migration is not: running `alembic
upgrade head` from N concurrently-starting API replicas is a race, even
though Alembic's own version table provides some protection. Migrations run
as an explicit, single step ahead of starting (or scaling) the API --
`apps/api/Dockerfile`'s `CMD` for this single-replica Compose setup (see
ADR-0009); a multi-replica deployment should use a dedicated one-shot
job/init container instead.

**Alternatives considered:** none seriously -- Alembic is the SQLAlchemy
ecosystem's standard migration tool and this repo already depends on
SQLAlchemy directly; introducing a different migration framework would add
a second ORM-adjacent dependency for no benefit.

**Revisit when:** never expected to be revisited; this is the steady-state
approach going forward. Each future schema change adds its own revision
file under `apps/api/alembic/versions/`.
