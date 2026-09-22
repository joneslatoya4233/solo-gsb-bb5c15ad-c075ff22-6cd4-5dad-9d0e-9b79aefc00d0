"""SQLite 数据访问层（原生 sqlite3，无 ORM 依赖）。"""

import json
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get(
    "DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "app.db")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    volume_l   REAL NOT NULL DEFAULT 0,
    ph         REAL NOT NULL DEFAULT 7,
    oxidizing  INTEGER NOT NULL DEFAULT 0,
    volatile   INTEGER NOT NULL DEFAULT 0,
    tags       TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scenarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _row_to_batch(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "volume_l": row["volume_l"],
        "ph": row["ph"],
        "oxidizing": bool(row["oxidizing"]),
        "volatile": bool(row["volatile"]),
        "tags": json.loads(row["tags"]),
    }


def list_batches():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM batches ORDER BY id").fetchall()
    return [_row_to_batch(r) for r in rows]


def create_batch(data):
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO batches (name, volume_l, ph, oxidizing, volatile, tags)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                data["name"], data["volume_l"], data["ph"],
                int(data["oxidizing"]), int(data["volatile"]),
                json.dumps(data["tags"], ensure_ascii=False),
            ),
        )
        row = conn.execute("SELECT * FROM batches WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_batch(row)


def delete_batch(batch_id):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        return cur.rowcount > 0


def clear_batches():
    with _connect() as conn:
        conn.execute("DELETE FROM batches")


def replace_batches(batches):
    """用给定批次整体替换当前工作区（场景恢复）。"""
    with _connect() as conn:
        conn.execute("DELETE FROM batches")
        conn.executemany(
            "INSERT INTO batches (name, volume_l, ph, oxidizing, volatile, tags)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    b["name"], b["volume_l"], b["ph"],
                    int(b["oxidizing"]), int(b["volatile"]),
                    json.dumps(b["tags"], ensure_ascii=False),
                )
                for b in batches
            ],
        )
    return list_batches()


def save_scenario(name, payload):
    """按名称保存场景（同名覆盖），payload 为可 JSON 序列化的 dict。"""
    text = json.dumps(payload, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO scenarios (name, payload) VALUES (?, ?)"
            " ON CONFLICT(name) DO UPDATE SET payload = excluded.payload,"
            " updated_at = datetime('now')",
            (name, text),
        )
        row = conn.execute("SELECT * FROM scenarios WHERE name = ?", (name,)).fetchone()
    return _row_to_scenario(row, with_payload=True)


def _row_to_scenario(row, with_payload=False):
    item = {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if with_payload:
        item["payload"] = json.loads(row["payload"])
    return item


def list_scenarios():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM scenarios ORDER BY updated_at DESC").fetchall()
    return [_row_to_scenario(r) for r in rows]


def get_scenario(scenario_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
    return _row_to_scenario(row, with_payload=True) if row else None


def delete_scenario(scenario_id):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
        return cur.rowcount > 0
