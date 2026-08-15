import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_ready_health_with_postgres_and_redis(run_integration: bool) -> None:
    from app.main import app

    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    except Exception as exc:
        if run_integration:
            raise
        pytest.skip(f"infrastructure unavailable: {exc}")

    if response.status_code != 200:
        if run_integration:
            pytest.fail(response.text)
        pytest.skip("PostgreSQL or Redis is not ready")

    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
