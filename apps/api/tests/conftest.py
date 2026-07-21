"""
Shared pytest fixtures.

Milestone 1 fixtures (`client`) plus Milestone 2's `registered_client`,
which registers a fresh user/workspace and returns an authenticated
TestClient (the auth cookie persists across requests on the same
TestClient instance, same as a browser session). Fixtures specific to
later features (sample PDF generation, etc.) still live in their own
milestone's test module -- see tests/pdf_helpers.py.

Milestone 4 change: the per-test schema reset now runs the real Alembic
migration chain (`alembic upgrade head`) against a fresh SQLite file instead
of calling Base.metadata.create_all/drop_all directly. This is a deliberate
upgrade, not just a mechanical swap: every test run now also proves the
migrations in alembic/versions/ actually produce a schema the app can run
against, which create_all could never catch (create_all only ever reflected
the models, never the migration chain -- the two could silently drift).
"""

import os
import tempfile

_TEST_DIR = tempfile.mkdtemp(prefix="khub_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"
# Deliberately point at a port nothing is listening on so the readiness
# test can exercise the real "dependency unreachable" code path rather
# than mocking it.
os.environ["QDRANT_URL"] = "http://localhost:1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

_ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")


def _alembic_config() -> Config:
    cfg = Config(_ALEMBIC_INI)
    # Belt-and-suspenders: env.py already reads DATABASE_URL from
    # app.core.config.get_settings(), but pinning it here too means this
    # fixture is correct even if env.py's settings resolution ever changes.
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return cfg


@pytest.fixture(autouse=True)
def _reset_state():
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    # SQLite: drop every table the previous test left behind (fresh file per
    # process, but _reset_state runs once per test) before re-applying
    # migrations from empty, mirroring the old drop_all/create_all semantics
    # exactly -- each test still gets a genuinely empty, freshly-migrated
    # schema, not an incrementally-upgraded one.
    with engine.begin() as connection:
        table_names = [
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            )
        ]
        for table_name in table_names:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))

    command.upgrade(_alembic_config(), "head")
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_client(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "demo@knowledgehub.ai", "password": "password123", "displayName": "Demo User"},
    )
    assert resp.status_code == 201, resp.text
    return client, resp.json()
