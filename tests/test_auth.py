import pytest
from fastapi.testclient import TestClient

from server import config
from server import main as app_module

TOKEN = "secret-token-for-tests"


@pytest.fixture()
def guarded_client(monkeypatch):
    monkeypatch.setattr(config, "ACCESS_TOKEN", TOKEN)
    with TestClient(app_module.app) as client:
        yield client


def test_health_reports_auth_required(guarded_client):
    data = guarded_client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["auth_required"] is True


def test_home_page_stays_public(guarded_client):
    assert guarded_client.get("/").status_code == 200


def test_protected_endpoint_requires_token(guarded_client):
    response = guarded_client.post("/api/datasets/demo")
    assert response.status_code == 401
    assert "口令" in response.json()["detail"]


def test_wrong_token_rejected(guarded_client):
    response = guarded_client.get("/api/auth", headers={"X-Access-Token": "wrong"})
    assert response.status_code == 401


def test_token_via_header(guarded_client):
    response = guarded_client.post(
        "/api/datasets/demo", headers={"X-Access-Token": TOKEN}
    )
    assert response.status_code == 200, response.text
    assert response.json()["dataset"]["rows"] > 0


def test_token_via_query_string(guarded_client):
    created = guarded_client.post(
        "/api/datasets/demo", headers={"X-Access-Token": TOKEN}
    ).json()
    dataset_id = created["dataset"]["id"]

    response = guarded_client.get(f"/api/datasets/{dataset_id}?token={TOKEN}")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == dataset_id
