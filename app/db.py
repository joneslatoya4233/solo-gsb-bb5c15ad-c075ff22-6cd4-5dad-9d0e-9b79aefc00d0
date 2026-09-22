"""SQLite 持久化层（标准库 sqlite3，无额外依赖）。"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get(
    "APP_DB", str(Path(__file__).resolve().parent.parent / "data" / "app.db")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    ph REAL NOT NULL DEFAULT 7,
    oxidizing INTEGER NOT NULL DEFAULT 0,
    volatile INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(_SCHEMA)


def _row_to_batch(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "volume": row["volume"],
        "ph": row["ph"],
        "oxidizing": bool(row["oxidizing"]),
        "volatile": bool(row["volatile"]),
        "tags": json.loads(row["tags"]),
        "created_at": row["created_at"],
    }


# ---------- 批次 ----------

def list_batches():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM batches ORDER BY id").fetchall()
    return [_row_to_batch(r) for r in rows]


def create_batch(data):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO batches (name, volume, ph, oxidizing, volatile, tags, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data["name"], data["volume"], data["ph"],
             int(data["oxidizing"]), int(data["volatile"]),
             json.dumps(data["tags"], ensure_ascii=False), _now()),
        )
        row = conn.execute("SELECT * FROM batches WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_batch(row)


def delete_batch(batch_id):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    return cur.rowcount > 0


def clear_batches():
    with get_conn() as conn:
        conn.execute("DELETE FROM batches")


def replace_batches(batch_list):
    """用给定批次快照整体替换当前批次（场景恢复）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM batches")
        for b in batch_list:
            conn.execute(
                "INSERT INTO batches (name, volume, ph, oxidizing, volatile, tags, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (b["name"], b["volume"], b["ph"],
                 int(b["oxidizing"]), int(b["volatile"]),
                 json.dumps(b.get("tags") or [], ensure_ascii=False), _now()),
            )


# ---------- 场景 ----------

def save_scenario(name, payload):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scenarios (name, created_at, payload) VALUES (?, ?, ?)",
            (name, _now(), json.dumps(payload, ensure_ascii=False)),
        )
        row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_scenario(row)


def list_scenarios():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM scenarios ORDER BY id DESC").fetchall()
    return [_row_to_scenario(r, with_payload=False) for r in rows]


def get_scenario(scenario_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
    return _row_to_scenario(row) if row else None


def delete_scenario(scenario_id):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
    return cur.rowcount > 0


def _row_to_scenario(row, with_payload=True):
    item = {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
    }
    payload = json.loads(row["payload"])
    item["batch_count"] = len(payload.get("batches", []))
    if with_payload:
        item["payload"] = payload
    return item
