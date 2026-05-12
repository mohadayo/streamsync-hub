import os
import logging
import time
import uuid

from flask import Flask, request, jsonify, g
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway")

PROCESSOR_URL = os.environ.get("PROCESSOR_URL", "http://localhost:8081")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:3000")
MAX_EVENTS = int(os.environ.get("MAX_EVENTS", "10000"))
MAX_PAYLOAD_SIZE = int(os.environ.get("MAX_PAYLOAD_SIZE", str(1024 * 1024)))
MAX_TYPE_LENGTH = int(os.environ.get("MAX_TYPE_LENGTH", "256"))
DEFAULT_PAGE_LIMIT = int(os.environ.get("DEFAULT_PAGE_LIMIT", "50"))
MAX_PAGE_LIMIT = int(os.environ.get("MAX_PAGE_LIMIT", "500"))

ALLOWED_STATUSES = {"received", "processed", "process_failed", "process_error"}

events_store: list[dict] = []


@app.before_request
def assign_request_id():
    incoming = request.headers.get("X-Request-ID", "")
    if incoming:
        g.request_id = incoming
    else:
        g.request_id = str(uuid.uuid4())
    logger.info(
        "request_id=%s method=%s path=%s",
        g.request_id,
        request.method,
        request.path,
    )


@app.after_request
def add_request_id_header(response):
    response.headers["X-Request-ID"] = g.get("request_id", "")
    return response


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "gateway", "timestamp": time.time()})


@app.route("/api/events", methods=["POST"])
def create_event():
    content_length = request.content_length or 0
    if content_length > MAX_PAYLOAD_SIZE:
        logger.warning("Payload too large: %d bytes (max %d)", content_length, MAX_PAYLOAD_SIZE)
        return jsonify({"error": "Payload too large", "max_bytes": MAX_PAYLOAD_SIZE}), 413

    data = request.get_json()
    if not data:
        logger.warning("Received empty event payload")
        return jsonify({"error": "Request body is required"}), 400

    if "type" not in data:
        logger.warning("Event missing 'type' field")
        return jsonify({"error": "Field 'type' is required"}), 400

    raw_type = data["type"]
    if not isinstance(raw_type, str):
        logger.warning("Event 'type' is not a string: %r", type(raw_type).__name__)
        return jsonify({"error": "Field 'type' must be a string"}), 400

    event_type = raw_type.strip()
    if not event_type:
        logger.warning("Event 'type' is blank or whitespace only")
        return jsonify({"error": "Field 'type' must not be blank"}), 400

    if len(event_type) > MAX_TYPE_LENGTH:
        logger.warning("Event 'type' exceeds max length: %d > %d", len(event_type), MAX_TYPE_LENGTH)
        return jsonify({
            "error": "Field 'type' is too long",
            "max_length": MAX_TYPE_LENGTH,
        }), 400

    event = {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "payload": data.get("payload", {}),
        "timestamp": time.time(),
        "status": "received",
    }
    events_store.append(event)

    if len(events_store) > MAX_EVENTS:
        removed = len(events_store) - MAX_EVENTS
        del events_store[:removed]
        logger.info("Evicted %d old events (store capped at %d)", removed, MAX_EVENTS)

    logger.info("Event created: id=%s type=%s", event["id"], event["type"])

    try:
        resp = requests.post(
            f"{PROCESSOR_URL}/process",
            json=event,
            timeout=5,
        )
        if resp.status_code == 200:
            result = resp.json()
            event["status"] = "processed"
            event["result"] = result
            logger.info("Event processed: id=%s", event["id"])
        else:
            event["status"] = "process_failed"
            logger.error("Processor returned %d for event %s", resp.status_code, event["id"])
    except requests.exceptions.RequestException as e:
        event["status"] = "process_error"
        logger.error("Failed to reach processor for event %s: %s", event["id"], str(e))

    return jsonify(event), 201


def _parse_timestamp_arg(value: str, name: str):
    try:
        ts = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a numeric Unix timestamp")
    if ts < 0:
        raise ValueError(f"'{name}' must be non-negative")
    return ts


@app.route("/api/events", methods=["GET"])
def list_events():
    event_type = request.args.get("type")
    status = request.args.get("status")
    limit = request.args.get("limit", DEFAULT_PAGE_LIMIT, type=int)
    offset = request.args.get("offset", 0, type=int)
    since_raw = request.args.get("since")
    until_raw = request.args.get("until")

    if status is not None and status not in ALLOWED_STATUSES:
        logger.warning("Invalid status filter: %s", status)
        return jsonify({
            "error": "Invalid status",
            "allowed": sorted(ALLOWED_STATUSES),
        }), 400

    since = None
    until = None
    try:
        if since_raw is not None:
            since = _parse_timestamp_arg(since_raw, "since")
        if until_raw is not None:
            until = _parse_timestamp_arg(until_raw, "until")
    except ValueError as e:
        logger.warning("Invalid timestamp filter: %s", e)
        return jsonify({"error": str(e)}), 400

    if since is not None and until is not None and until < since:
        logger.warning("Invalid range: until=%s < since=%s", until, since)
        return jsonify({"error": "'until' must be greater than or equal to 'since'"}), 400

    if limit < 0:
        limit = DEFAULT_PAGE_LIMIT
    if limit > MAX_PAGE_LIMIT:
        limit = MAX_PAGE_LIMIT
    if offset < 0:
        offset = 0

    filtered = events_store
    if event_type:
        filtered = [e for e in filtered if e["type"] == event_type]
    if status:
        filtered = [e for e in filtered if e.get("status") == status]
    if since is not None:
        filtered = [e for e in filtered if e.get("timestamp", 0) >= since]
    if until is not None:
        filtered = [e for e in filtered if e.get("timestamp", 0) <= until]

    total = len(filtered)
    paginated = filtered[offset:offset + limit]

    return jsonify({
        "events": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.route("/api/events/<event_id>", methods=["GET"])
def get_event(event_id):
    for event in events_store:
        if event["id"] == event_id:
            return jsonify(event)
    logger.warning("Event not found: %s", event_id)
    return jsonify({"error": "Event not found"}), 404


@app.route("/api/events/<event_id>", methods=["DELETE"])
def delete_event(event_id):
    for i, event in enumerate(events_store):
        if event["id"] == event_id:
            deleted = events_store.pop(i)
            logger.info("Event deleted: id=%s type=%s", deleted["id"], deleted["type"])
            return jsonify({"message": "Event deleted", "event": deleted})
    logger.warning("Event not found for deletion: %s", event_id)
    return jsonify({"error": "Event not found"}), 404


@app.route("/api/stats", methods=["GET"])
def stats():
    event_type = request.args.get("type")
    status = request.args.get("status")
    since_raw = request.args.get("since")
    until_raw = request.args.get("until")

    if status is not None and status not in ALLOWED_STATUSES:
        logger.warning("Invalid status filter on stats: %s", status)
        return jsonify({
            "error": "Invalid status",
            "allowed": sorted(ALLOWED_STATUSES),
        }), 400

    since = None
    until = None
    try:
        if since_raw is not None:
            since = _parse_timestamp_arg(since_raw, "since")
        if until_raw is not None:
            until = _parse_timestamp_arg(until_raw, "until")
    except ValueError as e:
        logger.warning("Invalid timestamp filter on stats: %s", e)
        return jsonify({"error": str(e)}), 400

    if since is not None and until is not None and until < since:
        logger.warning("Invalid range on stats: until=%s < since=%s", until, since)
        return jsonify({"error": "'until' must be greater than or equal to 'since'"}), 400

    filtered = events_store
    if event_type:
        filtered = [e for e in filtered if e["type"] == event_type]
    if status:
        filtered = [e for e in filtered if e.get("status") == status]
    if since is not None:
        filtered = [e for e in filtered if e.get("timestamp", 0) >= since]
    if until is not None:
        filtered = [e for e in filtered if e.get("timestamp", 0) <= until]

    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for e in filtered:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    return jsonify({"total": len(filtered), "by_status": by_status, "by_type": by_type})


def create_app():
    return app


if __name__ == "__main__":
    port = int(os.environ.get("GATEWAY_PORT", 8080))
    logger.info("Starting gateway on port %d", port)
    app.run(host="0.0.0.0", port=port)
