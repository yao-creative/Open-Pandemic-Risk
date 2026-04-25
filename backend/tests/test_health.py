from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


@pytest.mark.integration_local
def test_healthz_ok():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.integration_local
def test_readyz_unconfigured_deps_is_not_ready():
    resp = client.get("/readyz")
    assert resp.status_code == 503
    data = resp.json()
    assert data["ready"] is False
    assert data["checks"]["db"] == "ok"
    assert data["checks"]["azure_openai"] == "error"
    assert data["checks"]["promed"] == "error"
