"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    """The health endpoint returns the expected service status."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "codecourt"}


def test_cors_allows_loopback_frontend_origin() -> None:
    response = client.options(
        "/analyze",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
