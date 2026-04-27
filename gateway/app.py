import os
import logging
import time
import uuid

from flask import Flask, request, jsonify
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

events_store: list[dict] = []


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "gateway", "timestamp": time.time()})


@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json()
    if not data:
        logger.warning("Received empty event payload")
        return jsonify({"error": "Request body is required"}), 400

    if "type" not in data:
        logger.warning("Event missing 'type' field")
        return jsonify({"error": "Field 'type' is required"}), 400

    event = {
        "id": str(uuid.uuid4()),
        "type": data["type"],
        "payload": data.get("payload", {}),
        "timestamp": time.time(),
        "status": "received",
    }
    events_store.append(event)
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


@app.route("/api/events", methods=["GET"])
def list_events():
    event_type = request.args.get("type")
    if event_type:
        filtered = [e for e in events_store if e["type"] == event_type]
        return jsonify(filtered)
    return jsonify(events_store)


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
    total = len(events_store)
    by_status = {}
    by_type = {}
    for e in events_store:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    return jsonify({"total": total, "by_status": by_status, "by_type": by_type})


def create_app():
    return app


if __name__ == "__main__":
    port = int(os.environ.get("GATEWAY_PORT", 8080))
    logger.info("Starting gateway on port %d", port)
    app.run(host="0.0.0.0", port=port)
