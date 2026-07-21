# ADR-0008: SQLAlchemy `create_all` instead of Alembic migrations

**Status:** Superseded by ADR-0010 (Milestone 4). Kept for history --
everything below was accurate for Milestones 1-3 and explains why this
decision was correct at the time.

**Decision:** Tables are created directly from the SQLAlchemy models on
API startup (`Base.metadata.create_all`). There is no migrations directory.

**Alternatives considered:** Alembic-managed, reviewable migrations are the
production-correct approach (and are what the full enterprise SRS
specifies) once a schema needs controlled, auditable changes across
environments with existing data.

**Why this wins for 2 days:** the schema is frozen for MVP (see the
Database Design section of the product freeze) and there is no existing
production data to migrate around. Introducing Alembic now would add
tooling without a corresponding benefit.

**MVP impact:** changing a model after data exists in a running instance
requires manually dropping/recreating tables (acceptable for local/demo
use; called out in the README).

**Revisit when:** the schema needs to evolve against data that must be
preserved — the first Phase 2 milestone that touches the database should
introduce Alembic at that point, not before.
