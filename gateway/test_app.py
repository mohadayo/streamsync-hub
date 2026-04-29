import json
import pytest
from app import app, events_store


@pytest.fixture(autouse=True)
def clear_events():
    events_store.clear()
    yield
    events_store.clear()


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
    assert "events" in data
    assert "total" in data
    assert data["total"] == 1
    assert len(data["events"]) == 1


def test_list_events_filter_by_type(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "filter.test"}),
        content_type="application/json",
    )
    client.post(
        "/api/events",
        data=json.dumps({"type": "other.type"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?type=filter.test")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["events"]) == 1
    for e in data["events"]:
        assert e["type"] == "filter.test"


def test_list_events_pagination_limit(client):
    for i in range(5):
        client.post(
            "/api/events",
            data=json.dumps({"type": f"page.test.{i}"}),
            content_type="application/json",
        )
    resp = client.get("/api/events?limit=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 5
    assert len(data["events"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0


def test_list_events_pagination_offset(client):
    for i in range(5):
        client.post(
            "/api/events",
            data=json.dumps({"type": f"page.test.{i}"}),
            content_type="application/json",
        )
    resp = client.get("/api/events?limit=2&offset=3")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 5
    assert len(data["events"]) == 2
    assert data["offset"] == 3
    assert data["events"][0]["type"] == "page.test.3"
    assert data["events"][1]["type"] == "page.test.4"


def test_list_events_pagination_offset_beyond(client):
    for i in range(3):
        client.post(
            "/api/events",
            data=json.dumps({"type": f"page.test.{i}"}),
            content_type="application/json",
        )
    resp = client.get("/api/events?limit=10&offset=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert len(data["events"]) == 0


def test_list_events_pagination_with_filter(client):
    for i in range(4):
        client.post(
            "/api/events",
            data=json.dumps({"type": "target"}),
            content_type="application/json",
        )
    client.post(
        "/api/events",
        data=json.dumps({"type": "other"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?type=target&limit=2&offset=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 4
    assert len(data["events"]) == 2


def test_list_events_negative_limit(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "neg.test"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?limit=-1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["events"]) == 1


def test_list_events_negative_offset(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "neg.test"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?offset=-5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["offset"] == 0


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


def test_delete_event_success(client):
    create_resp = client.post(
        "/api/events",
        data=json.dumps({"type": "test.delete"}),
        content_type="application/json",
    )
    event_id = create_resp.get_json()["id"]

    resp = client.delete(f"/api/events/{event_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Event deleted"
    assert data["event"]["id"] == event_id

    get_resp = client.get(f"/api/events/{event_id}")
    assert get_resp.status_code == 404


def test_delete_event_not_found(client):
    resp = client.delete("/api/events/nonexistent-id")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "not found" in data["error"].lower()


def test_delete_event_updates_stats(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "stat.del"}),
        content_type="application/json",
    )
    create_resp = client.post(
        "/api/events",
        data=json.dumps({"type": "stat.del"}),
        content_type="application/json",
    )
    event_id = create_resp.get_json()["id"]

    stats_before = client.get("/api/stats").get_json()
    assert stats_before["total"] == 2

    client.delete(f"/api/events/{event_id}")

    stats_after = client.get("/api/stats").get_json()
    assert stats_after["total"] == 1


def test_stats(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 0
    assert "by_status" in data
    assert "by_type" in data


def test_stats_with_events(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "stat.test"}),
        content_type="application/json",
    )
    client.post(
        "/api/events",
        data=json.dumps({"type": "stat.test"}),
        content_type="application/json",
    )
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    assert data["by_type"]["stat.test"] == 2


def test_events_store_max_capacity(client, monkeypatch):
    monkeypatch.setattr("app.MAX_EVENTS", 3)
    for i in range(5):
        client.post(
            "/api/events",
            data=json.dumps({"type": f"cap.test.{i}"}),
            content_type="application/json",
        )
    resp = client.get("/api/events")
    data = resp.get_json()
    assert data["total"] == 3
    types = [e["type"] for e in data["events"]]
    assert "cap.test.0" not in types
    assert "cap.test.1" not in types
    assert "cap.test.4" in types


def test_payload_too_large(client, monkeypatch):
    monkeypatch.setattr("app.MAX_PAYLOAD_SIZE", 50)
    large_payload = json.dumps({"type": "test", "payload": {"data": "x" * 100}})
    resp = client.post(
        "/api/events",
        data=large_payload,
        content_type="application/json",
    )
    assert resp.status_code == 413
    data = resp.get_json()
    assert "too large" in data["error"].lower()


def test_payload_within_limit(client, monkeypatch):
    monkeypatch.setattr("app.MAX_PAYLOAD_SIZE", 10000)
    resp = client.post(
        "/api/events",
        data=json.dumps({"type": "small.event"}),
        content_type="application/json",
    )
    assert resp.status_code == 201
