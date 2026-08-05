"""投递历史记忆（SQLite，MVP 极简版）。

供去重、跟踪、复盘。后续增强：定时收集器查重、投递漏斗跟踪。
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    jd_id           TEXT,
    company         TEXT,
    role            TEXT,
    status          TEXT,        -- seen / analyzed / applied / rejected / offer
    match_score     REAL,
    needs_proof_items TEXT,      -- JSON 数组，缺证据项
    applied_at      TEXT
);
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def add_application(jd_id: str, company: str, role: str, status: str = "seen",
                    match_score: float | None = None, needs_proof_items: str = "[]") -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO applications (jd_id, company, role, status, match_score, needs_proof_items, applied_at)"
        " VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (jd_id, company, role, status, match_score, needs_proof_items),
    )
    conn.commit()
    conn.close()


def is_seen(jd_id: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT 1 FROM applications WHERE jd_id = ? LIMIT 1", (jd_id,)).fetchone()
    conn.close()
    return row is not None


def list_applications(limit: int = 50) -> list[tuple]:
    conn = _connect()
    rows = conn.execute(
        "SELECT jd_id, company, role, status, match_score, applied_at"
        " FROM applications ORDER BY applied_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows
