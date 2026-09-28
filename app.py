import json
import logging
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request

from config import (
    HOST, PORT, DEVICE_SECRETS, LOG_PATH, RETRY_INTERVAL_SECONDS,
    MAX_RETRY_ATTEMPTS, CLOUD_ENDPOINT
)
from forwarder import forward_payload
from security import verify_signature
from storage import (
    init_db, add_record, mark_forwarded, mark_failed, get_pending,
    get_recent_records, add_event, get_recent_events, counts, backup_database
)

app = Flask(__name__)

Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
logger = logging.getLogger("gateway")


def validate_payload(payload):
    if not isinstance(payload, dict):
        return False, "JSON object required"
    # Intentionally generic: these fields identify a monitoring message without
    # making the gateway responsible for sensor accuracy or THI calculations.
    required = ["timestamp", "data"]
    missing = [k for k in required if k not in payload]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    if not isinstance(payload["data"], dict):
        return False, "data must be an object"
    return True, None


def try_forward(record_id, payload_text):
    try:
        latency_ms = forward_payload(payload_text)
        mark_forwarded(record_id, latency_ms)
        add_event("forward_success", f"Record {record_id} forwarded in {latency_ms:.1f} ms")
        logger.info("Record %s forwarded", record_id)
        return True, latency_ms
    except Exception as exc:
        mark_failed(record_id, exc)
        add_event("forward_failed", f"Record {record_id}: {exc}")
        logger.warning("Forward failed for record %s: %s", record_id, exc)
        return False, None


def retry_worker():
    while True:
        try:
            for row in get_pending(limit=100):
                if row["attempts"] >= MAX_RETRY_ATTEMPTS:
                    continue
                try_forward(row["id"], row["payload"])
        except Exception as exc:
            logger.exception("Retry worker error: %s", exc)
        time.sleep(RETRY_INTERVAL_SECONDS)


@app.get("/")
def home():
    return jsonify({
        "name": "Secure Low-Cost IoT Network Gateway for POULTRYVANTAGE",
        "status": "running",
        "cloud_configured": bool(CLOUD_ENDPOINT),
    })


@app.post("/api/data")
def receive_data():
    device_id = request.headers.get("X-Device-ID", "").strip()
    signature = request.headers.get("X-Signature", "").strip()
    raw_body = request.get_data(cache=True)

    if not device_id or device_id not in DEVICE_SECRETS:
        add_event("auth_rejected", f"Unknown device/source: {device_id or '[missing]'}")
        return jsonify({"ok": False, "error": "unauthorized device/source"}), 401

    if not verify_signature(DEVICE_SECRETS[device_id], raw_body, signature):
        add_event("auth_rejected", f"Invalid signature for {device_id}")
        return jsonify({"ok": False, "error": "invalid signature"}), 401

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"ok": False, "error": "invalid JSON"}), 400

    valid, error = validate_payload(payload)
    if not valid:
        add_event("validation_failed", f"{device_id}: {error}")
        return jsonify({"ok": False, "error": error}), 400

    payload_text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    record_id = add_record(device_id, payload_text)
    add_event("data_received", f"Record {record_id} accepted from {device_id}")

    forwarded, latency_ms = try_forward(record_id, payload_text)
    return jsonify({
        "ok": True,
        "record_id": record_id,
        "device_id": device_id,
        "status": "forwarded" if forwarded else "buffered",
        "latency_ms": latency_ms,
    }), 200 if forwarded else 202


@app.get("/api/status")
def status():
    return jsonify({
        "gateway": "online",
        "cloud_endpoint_configured": bool(CLOUD_ENDPOINT),
        "records": counts(),
        "authorized_sources": list(DEVICE_SECRETS.keys()),
    })


@app.get("/api/records")
def records():
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify(get_recent_records(limit))


@app.get("/api/logs")
def logs():
    limit = min(int(request.args.get("limit", 100)), 500)
    return jsonify(get_recent_events(limit))


@app.post("/api/retry")
def retry_now():
    attempted = 0
    forwarded = 0
    for row in get_pending(limit=100):
        if row["attempts"] >= MAX_RETRY_ATTEMPTS:
            continue
        attempted += 1
        ok, _ = try_forward(row["id"], row["payload"])
        forwarded += int(ok)
    return jsonify({"attempted": attempted, "forwarded": forwarded})


@app.post("/api/backup")
def backup():
    try:
        path = backup_database()
        add_event("backup_created", path)
        return jsonify({"ok": True, "backup": path})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    init_db()
    add_event("gateway_started", f"Gateway started on {HOST}:{PORT}")
    threading.Thread(target=retry_worker, daemon=True).start()
    app.run(host=HOST, port=PORT, debug=False)
