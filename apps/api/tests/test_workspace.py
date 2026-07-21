"""
Milestone 2 (Authentication) tests: workspace + user profile endpoints.
"""


def test_get_workspace_requires_auth(client):
    resp = client.get("/api/v1/workspace")
    assert resp.status_code == 401


def test_get_workspace_returns_own_workspace(registered_client):
    client, body = registered_client
    resp = client.get("/api/v1/workspace")
    assert resp.status_code == 200
    assert resp.json()["workspace"]["id"] == body["workspace"]["id"]
    assert resp.json()["workspace"]["name"] == "Demo User's Workspace"


def test_update_workspace_name(registered_client):
    client, _ = registered_client
    resp = client.patch("/api/v1/workspace", json={"name": "Renamed Workspace"})
    assert resp.status_code == 200
    assert resp.json()["workspace"]["name"] == "Renamed Workspace"

    # The rename is persisted, not just echoed back.
    follow_up = client.get("/api/v1/workspace")
    assert follow_up.json()["workspace"]["name"] == "Renamed Workspace"


def test_update_workspace_rejects_empty_name(registered_client):
    client, _ = registered_client
    resp = client.patch("/api/v1/workspace", json={"name": ""})
    assert resp.status_code == 422


def test_update_profile_display_name(registered_client):
    client, _ = registered_client
    resp = client.patch("/api/v1/users/me", json={"displayName": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["user"]["displayName"] == "New Name"

    me = client.get("/api/v1/auth/me")
    assert me.json()["user"]["displayName"] == "New Name"


def test_workspace_isolation_between_users(client):
    # Two independent sessions must never see each other's workspace.
    client.post(
        "/api/v1/auth/register",
        json={"email": "x@x.com", "password": "password123", "displayName": "X User"},
    )
    workspace_x = client.get("/api/v1/workspace").json()["workspace"]

    from fastapi.testclient import TestClient

    from app.main import app

    client_y = TestClient(app)
    client_y.post(
        "/api/v1/auth/register",
        json={"email": "y@y.com", "password": "password123", "displayName": "Y User"},
    )
    workspace_y = client_y.get("/api/v1/workspace").json()["workspace"]

    assert workspace_x["id"] != workspace_y["id"]
