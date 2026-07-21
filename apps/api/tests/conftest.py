"""
Shared pytest fixtures.

Milestone 1 fixtures (`client`) plus Milestone 2's `registered_client`,
which registers a fresh user/workspace and returns an authenticated
TestClient (the auth cookie persists across requests on the same
TestClient instance, same as a browser session). Fixtures specific to
later features (sample PDF generation, etc.) still live in their own
milestone's test module -- see tests/pdf_helpers.py.
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


@pytest.fixture
def registered_client(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "demo@knowledgehub.ai", "password": "password123", "displayName": "Demo User"},
    )
    assert resp.status_code == 201, resp.text
    return client, resp.json()
