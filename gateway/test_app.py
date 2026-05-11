import json
import uuid
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


def test_list_events_filter_by_status(client):
    create_resp = client.post(
        "/api/events",
        data=json.dumps({"type": "status.test"}),
        content_type="application/json",
    )
    assert create_resp.status_code == 201
    created_status = create_resp.get_json()["status"]

    resp = client.get(f"/api/events?status={created_status}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1
    for e in data["events"]:
        assert e["status"] == created_status


def test_list_events_filter_by_status_no_match(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "status.nomatch"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?status=received")
    assert resp.status_code == 200
    data = resp.get_json()
    for e in data["events"]:
        assert e["status"] == "received"


def test_list_events_invalid_status(client):
    resp = client.get("/api/events?status=bogus")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "allowed" in data
    assert "received" in data["allowed"]


def test_list_events_status_combined_with_type(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "alpha"}),
        content_type="application/json",
    )
    client.post(
        "/api/events",
        data=json.dumps({"type": "beta"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?type=alpha&status=process_error")
    assert resp.status_code == 200
    data = resp.get_json()
    for e in data["events"]:
        assert e["type"] == "alpha"
        assert e["status"] == "process_error"


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


def test_stats_filter_by_type(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "stat.a"}),
        content_type="application/json",
    )
    client.post(
        "/api/events",
        data=json.dumps({"type": "stat.b"}),
        content_type="application/json",
    )
    resp = client.get("/api/stats?type=stat.a")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert data["by_type"] == {"stat.a": 1}


def test_stats_filter_by_status(client):
    events_store.append({
        "id": "1", "type": "x", "payload": {}, "timestamp": 100.0, "status": "received",
    })
    events_store.append({
        "id": "2", "type": "x", "payload": {}, "timestamp": 200.0, "status": "processed",
    })
    resp = client.get("/api/stats?status=processed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert data["by_status"] == {"processed": 1}


def test_stats_filter_by_time_range(client):
    events_store.append({
        "id": "1", "type": "x", "payload": {}, "timestamp": 100.0, "status": "received",
    })
    events_store.append({
        "id": "2", "type": "x", "payload": {}, "timestamp": 200.0, "status": "received",
    })
    events_store.append({
        "id": "3", "type": "x", "payload": {}, "timestamp": 300.0, "status": "received",
    })
    resp = client.get("/api/stats?since=150&until=250")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1


def test_stats_invalid_status(client):
    resp = client.get("/api/stats?status=bogus")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "allowed" in data


def test_stats_invalid_since(client):
    resp = client.get("/api/stats?since=notanumber")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "since" in data["error"]


def test_stats_until_before_since(client):
    resp = client.get("/api/stats?since=200&until=100")
    assert resp.status_code == 400


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


def test_list_events_filter_since(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "ts.test"}),
        content_type="application/json",
    )
    # All events should be present when since is in the past
    resp = client.get("/api/events?since=0")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 1

    # since far in the future returns nothing
    resp = client.get("/api/events?since=99999999999")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_list_events_filter_until(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "ts.test"}),
        content_type="application/json",
    )
    # until far in the future includes everything
    resp = client.get("/api/events?until=99999999999")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 1

    # until in the past excludes everything
    resp = client.get("/api/events?until=0")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_list_events_filter_since_and_until_combined(client):
    client.post(
        "/api/events",
        data=json.dumps({"type": "ts.combo"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?since=0&until=99999999999")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 1


def test_list_events_invalid_since(client):
    resp = client.get("/api/events?since=notanumber")
    assert resp.status_code == 400
    assert "since" in resp.get_json()["error"]


def test_list_events_negative_since(client):
    resp = client.get("/api/events?since=-1")
    assert resp.status_code == 400


def test_list_events_invalid_until(client):
    resp = client.get("/api/events?until=abc")
    assert resp.status_code == 400
    assert "until" in resp.get_json()["error"]


def test_list_events_until_before_since(client):
    resp = client.get("/api/events?since=100&until=50")
    assert resp.status_code == 400
    assert "until" in resp.get_json()["error"].lower()


def test_list_events_limit_capped_at_max(client, monkeypatch):
    monkeypatch.setattr("app.MAX_PAGE_LIMIT", 5)
    for i in range(10):
        client.post(
            "/api/events",
            data=json.dumps({"type": f"cap.{i}"}),
            content_type="application/json",
        )
    resp = client.get("/api/events?limit=100")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["limit"] == 5
    assert len(data["events"]) == 5
    assert data["total"] == 10


def test_list_events_limit_under_max_unaffected(client, monkeypatch):
    monkeypatch.setattr("app.MAX_PAGE_LIMIT", 100)
    client.post(
        "/api/events",
        data=json.dumps({"type": "norm"}),
        content_type="application/json",
    )
    resp = client.get("/api/events?limit=10")
    assert resp.status_code == 200
    assert resp.get_json()["limit"] == 10


def test_request_id_generated(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    request_id = resp.headers.get("X-Request-ID")
    assert request_id is not None
    uuid.UUID(request_id)


def test_request_id_forwarded(client):
    custom_id = "custom-trace-id-12345"
    resp = client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_id


def test_request_id_unique_per_request(client):
    resp1 = client.get("/health")
    resp2 = client.get("/health")
    id1 = resp1.headers.get("X-Request-ID")
    id2 = resp2.headers.get("X-Request-ID")
    assert id1 != id2


def test_request_id_on_error_response(client):
    resp = client.get("/api/events/nonexistent-id")
    assert resp.status_code == 404
    assert resp.headers.get("X-Request-ID") is not None
