from fastapi.testclient import TestClient

from app.main import create_app


def test_live_health_does_not_require_infrastructure() -> None:
    client = TestClient(create_app(with_lifespan=False))
    response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "job-agent"
    assert body["checks"]["api"] == "ok"
    assert body["checks"]["database"] == "skipped"
    assert body["checks"]["redis"] == "skipped"


def test_ready_health_is_degraded_without_infrastructure() -> None:
    client = TestClient(create_app(with_lifespan=False))
    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error"
    assert body["checks"]["redis"] == "error"
    assert "database" in body["errors"]
    assert "redis" in body["errors"]


def test_combined_health_matches_readiness() -> None:
    client = TestClient(create_app(with_lifespan=False))
    ready = client.get("/health/ready").json()
    combined = client.get("/health").json()
    assert combined["status"] == ready["status"]
    assert combined["checks"] == ready["checks"]
