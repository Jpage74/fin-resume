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

# 反馈回路：用户对分析报告的评价落库，驱动 prompt/检索迭代
_FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT,
    role_category TEXT,
    company       TEXT,
    role_name     TEXT,
    match_score   REAL,
    verdict       TEXT,
    rating        TEXT,        -- 有用 / 不准
    comment       TEXT         -- 用户补充说明（原话）
);
"""


def _connect(path: Path | None = None):
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.execute(_SCHEMA)
    conn.execute(_FEEDBACK_SCHEMA)
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


def add_feedback(
    rating: str,
    comment: str = "",
    *,
    role_category: str = "",
    company: str = "",
    role_name: str = "",
    match_score: float | None = None,
    verdict: str = "",
    db_path: Path | None = None,
) -> None:
    """记录一条用户反馈（rating：有用 / 不准），关联最近一次分析的岗位信息。"""
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO feedback (created_at, role_category, company, role_name, match_score, verdict, rating, comment)"
        " VALUES (datetime('now','localtime'), ?, ?, ?, ?, ?, ?, ?)",
        (role_category, company, role_name, match_score, verdict, rating, comment),
    )
    conn.commit()
    conn.close()


def list_feedback(limit: int = 50, db_path: Path | None = None) -> list[tuple]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT created_at, role_name, company, rating, comment FROM feedback ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def feedback_stats(db_path: Path | None = None) -> dict:
    """按 rating 汇总：总数 / 有用数 / 不准数 / 不准率。"""
    conn = _connect(db_path)
    total, useful, bad = conn.execute(
        "SELECT COUNT(*),"
        " SUM(CASE WHEN rating='有用' THEN 1 ELSE 0 END),"
        " SUM(CASE WHEN rating='不准' THEN 1 ELSE 0 END)"
        " FROM feedback"
    ).fetchone()
    conn.close()
    total = total or 0
    useful = useful or 0
    bad = bad or 0
    return {"total": total, "useful": useful, "inaccurate": bad,
            "inaccurate_rate": round(bad / total, 4) if total else 0.0}
