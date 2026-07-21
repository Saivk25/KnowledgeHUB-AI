"""
Shared pytest fixtures -- Milestone 1 (Project Foundation) scope.

Only what the foundation needs: an isolated SQLite database per test run
and a FastAPI TestClient. Fixtures specific to later features (sample PDF
generation, authenticated clients, etc.) live in their own milestone's test
module so this file doesn't accumulate dependencies for features that
don't exist yet.
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

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)
