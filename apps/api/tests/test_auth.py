"""
Milestone 2 (Authentication) tests: registration, login, session cookie
handling, and the protected /me endpoint.
"""


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


def test_register_rejects_short_password(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "short@b.com", "password": "short", "displayName": "Shorty"},
    )
    assert resp.status_code == 422


def test_register_rejects_invalid_email(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "password123", "displayName": "Bad Email"},
    )
    assert resp.status_code == 422


def test_login_wrong_password_returns_401(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "c@d.com", "password": "password123", "displayName": "Cee"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "c@d.com", "password": "wrongpass"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_returns_401_not_404(client):
    # Deliberately the same error as a wrong password: this endpoint must
    # not reveal whether an email address has an account.
    resp = client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.com", "password": "whatever123"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_succeeds_with_correct_credentials(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "e@f.com", "password": "password123", "displayName": "Eff"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "e@f.com", "password": "password123"})
    assert resp.status_code == 200
    assert resp.json()["accessToken"]


def test_protected_route_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_returns_current_user(registered_client):
    client, _ = registered_client
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "demo@knowledgehub.ai"


def test_bearer_token_also_authenticates(registered_client):
    # Confirms the API works for non-browser clients too, not just the
    # cookie set on the TestClient session.
    client, body = registered_client
    token = body["accessToken"]
    fresh_client_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert fresh_client_resp.status_code == 200


def test_logout_clears_session(registered_client):
    client, _ = registered_client
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204

    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401


def test_password_is_hashed_not_stored_in_plaintext(registered_client):
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@knowledgehub.ai").first()
        assert user is not None
        assert user.password_hash != "password123"
        assert user.password_hash.startswith("$2b$")  # bcrypt hash prefix
    finally:
        db.close()
