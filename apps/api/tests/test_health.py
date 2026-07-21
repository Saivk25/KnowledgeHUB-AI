"""
Milestone 1 (Project Foundation) tests.

Covers the only two endpoints that exist at this stage: liveness and
readiness. The readiness test deliberately runs against an unreachable
Qdrant URL (set in conftest.py) so it exercises the real "dependency is
down" code path -- a health check whose failure branch was never actually
tested is not a trustworthy health check.
"""


def test_liveness_always_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "KnowledgeHub AI"


def test_readiness_reports_database_up(client):
    resp = client.get("/health/ready")
    body = resp.json()
    # SQLite (the test database) is always reachable, so this component
    # must report up regardless of the overall status.
    assert body["components"]["database"]["status"] == "up"


def test_readiness_reports_qdrant_down_and_returns_503(client):
    resp = client.get("/health/ready")
    body = resp.json()
    assert resp.status_code == 503
    assert body["status"] == "degraded"
    assert body["components"]["vector_db"]["status"] == "down"


def test_readiness_response_shape_is_stable(client):
    resp = client.get("/health/ready")
    body = resp.json()
    assert set(body.keys()) == {"status", "components"}
    assert set(body["components"].keys()) == {"database", "vector_db"}
    for component in body["components"].values():
        assert set(component.keys()) == {"status", "detail"}
