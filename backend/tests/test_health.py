from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_ok():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_unconfigured_azure_is_not_ready():
    resp = client.get("/readyz")
    assert resp.status_code == 503
    data = resp.json()
    assert data["ready"] is False
    assert data["checks"]["db"] == "ok"
    assert data["checks"]["azure_openai"] == "error"
