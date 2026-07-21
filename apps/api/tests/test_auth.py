"""
Deferred to Milestone 2 (Authentication).

These tests exercise the `/api/v1/auth` router, which is not mounted in
Milestone 1 (Project Foundation) -- see app/main.py. Skipped as a whole
module rather than deleted so the exact intended behavior is already
specified and ready to re-enable (just delete `pytestmark` below) once
Milestone 2 wires the auth router back into the app.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Auth router not mounted until Milestone 2")


def test_register_creates_user_and_workspace(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "password123", "displayName": "Ada"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "a@b.com"
    assert body["workspace"]["name"] == "Ada's Workspace"
    assert body["accessToken"]


def test_duplicate_email_is_rejected(client):
    payload = {"email": "dup@b.com", "password": "password123", "displayName": "Dup"}
    client.post("/api/v1/auth/register", json=payload)
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


def test_login_wrong_password_returns_401(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "c@d.com", "password": "password123", "displayName": "Cee"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "c@d.com", "password": "wrongpass"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_protected_route_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(registered_client):
    client, _ = registered_client
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "demo@knowledgehub.ai"
