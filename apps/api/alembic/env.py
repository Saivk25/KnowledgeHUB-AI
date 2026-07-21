"""
Alembic environment.

Decision: pull DATABASE_URL from app.core.config.get_settings() rather than
duplicating it in alembic.ini. Why: this repo already has one settings
object that reads DATABASE_URL from the environment / .env (see
app/core/config.py); a second, independently-configured connection string
in alembic.ini would be exactly the kind of drift Alembic is being
introduced to prevent (see docs/adr/0010-alembic-migrations.md).

`target_metadata` points at app.db.base.Base.metadata so `alembic revision
--autogenerate` has something to diff against for future migrations, but
autogenerate is a drafting aid only -- every migration in versions/ is
still hand-reviewed before being committed (same review bar as any other
schema change in this repo).

Bug fixed during Milestone 4 verification: this used to unconditionally
overwrite `sqlalchemy.url` from `get_settings().DATABASE_URL` even when a
caller had already set one explicitly on the `Config` object (e.g.
tests/conftest.py's `_alembic_config()` and
tests/test_alembic_migrations.py's `_alembic_config()`, both of which build
a `Config` and call `cfg.set_main_option("sqlalchemy.url", ...)` before
invoking `command.upgrade()`). Because `get_settings()` is `@lru_cache`d
process-wide, once anything imports `app.main` (which happens on
conftest.py's very first import), the cached Settings object's
`DATABASE_URL` -- from whatever `os.environ["DATABASE_URL"]` was at that
moment -- silently overrode every other database the test suite tried to
point Alembic at afterwards. `test_alembic_migrations.py`'s three tests each
build their own scratch SQLite file specifically to test the migration
chain in isolation; the override meant every one of them silently ran (or
no-op'd) against the shared conftest test database instead, producing
either "no tables in the scratch db" or "no such table: documents" (the
scratch db was empty; the conftest db was already migrated to head).
Fixed by only falling back to `settings.DATABASE_URL` when the `Config`
doesn't already have a URL -- true for `alembic.ini`'s CLI usage
(`sqlalchemy.url =` is blank there) and for Docker/production, false for any
caller that explicitly configured its own URL.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app's models package so every model is registered on
# Base.metadata before we hand it to Alembic -- otherwise autogenerate would
# silently see an empty/partial schema for any model not already imported by
# whatever happened to run first (see app/models/__init__.py, which is the
# canonical "these are all the models" list for exactly this reason).
from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection.

    render_as_batch=True: this project runs on both SQLite (local dev/tests,
    per app/db/session.py's documented dual-backend decision) and Postgres
    (Docker/production). SQLite cannot ALTER a column or foreign key
    in-place, so every ALTER in versions/ uses `op.batch_alter_table(...)`,
    which requires batch mode to be on for autogenerate/offline rendering
    too. On Postgres, batch mode degrades to the equivalent direct ALTER
    statements -- it is a no-op behaviorally, not a compromise.
    """

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
