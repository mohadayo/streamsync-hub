import json
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert "timestamp" in data


def test_create_event_success(client):
    resp = client.post(
        "/api/events",
        data=json.dumps({"type": "user.signup", "payload": {"user": "alice"}}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["type"] == "user.signup"
    assert "id" in data
    assert data["payload"] == {"user": "alice"}


def test_create_event_missing_body(client):
    resp = client.post("/api/events", content_type="application/json")
    assert resp.status_code == 400


def test_create_event_missing_type(client):
    resp = client.post(
        "/api/events",
        data=json.dumps({"payload": {}}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "type" in data["error"].lower()


def test_list_events(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "test.list"}),
        content_type="application/json",
    )
    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_events_filter_by_type(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "filter.test"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?type=filter.test")
    assert resp.status_code == 200
    data = resp.get_json()
    for e in data:
        assert e["type"] == "filter.test"


def test_get_event_not_found(client):
    resp = client.get("/api/events/nonexistent-id")
    assert resp.status_code == 404


def test_get_event_by_id(client):
    create_resp = client.post(
        "/api/events",
        data=json.dumps({"type": "test.getbyid"}),
        content_type="application/json",
    )
    event_id = create_resp.get_json()["id"]
    resp = client.get(f"/api/events/{event_id}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == event_id


def test_stats(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "total" in data
    assert "by_status" in data
    assert "by_type" in data
