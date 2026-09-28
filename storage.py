import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DB_PATH, BACKUP_DIR


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                received_at TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                forwarded_at TEXT,
                latency_ms REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def add_record(device_id, payload_text, status="buffered"):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO records (device_id, payload, received_at, status) VALUES (?, ?, ?, ?)",
            (device_id, payload_text, utcnow(), status),
        )
        return cur.lastrowid


def mark_forwarded(record_id, latency_ms=None):
    with connect() as conn:
        conn.execute(
            "UPDATE records SET status='forwarded', forwarded_at=?, last_error=NULL, latency_ms=? WHERE id=?",
            (utcnow(), latency_ms, record_id),
        )


def mark_failed(record_id, error):
    with connect() as conn:
        conn.execute(
            "UPDATE records SET status='buffered', attempts=attempts+1, last_error=? WHERE id=?",
            (str(error)[:500], record_id),
        )


def get_pending(limit=100):
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM records WHERE status='buffered' ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()]


def get_recent_records(limit=50):
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM records ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]


def add_event(event_type, message):
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (event_type, message, created_at) VALUES (?, ?, ?)",
            (event_type, message, utcnow()),
        )


def get_recent_events(limit=100):
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]


def counts():
    with connect() as conn:
        result = {"total": 0, "forwarded": 0, "buffered": 0}
        for row in conn.execute("SELECT status, COUNT(*) AS c FROM records GROUP BY status"):
            result[row["status"]] = row["c"]
            result["total"] += row["c"]
        return result


def backup_database():
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"gateway_{stamp}.db")
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, dst)
        return dst
    raise FileNotFoundError(DB_PATH)
