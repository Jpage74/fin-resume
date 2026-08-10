"""短期记忆（STM，极简版）：最近窗口内的对话原文，不做 LLM 压缩。

设计：MVP 用「最近 N 条消息原文」替代 LLM 压缩——低成本、零额外模型调用。
数据源是 ADK 自动生成的 session.db（agents/fin_resume/.adk/session.db），
它持久化了全部会话的 events（含 author / role / text / timestamp）。

窗口逻辑：默认取「过去 20 分钟内」所有会话产生的对话原文（最多 N 条），
会话创建时读取并注入 prompt，给新会话提供短期连续性。

存储：data/memory/stm_ctx.json —— {built_at, window_minutes, messages: [...]}
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from job_assistant.paths import MEMORY_DIR, SESSION_DB  # noqa: E402

DEFAULT_WINDOW_MINUTES = 20
DEFAULT_MAX_MESSAGES = 10

STM_PATH = MEMORY_DIR / "stm_ctx.json"


def _extract_text(event_data: str) -> str:
    """从 event_data JSON 里取出可读文本（user 消息 / model 回复），过滤工具事件。"""
    try:
        ev = json.loads(event_data)
    except json.JSONDecodeError:
        return ""
    content = ev.get("content") or {}
    parts = content.get("parts") or []
    texts = []
    for p in parts:
        if "text" in p:
            texts.append(p["text"])
        elif "functionCall" in p or "functionResponse" in p:
            continue  # 工具调用事件跳过，记忆只保留人话
    return "\n".join(texts).strip()


def _is_user_msg(ev: dict) -> bool:
    return ev.get("content", {}).get("role") == "user"


def _is_model_reply(ev: dict) -> bool:
    return ev.get("content", {}).get("role") == "model"


def read_recent_messages(
    db_path: Path = SESSION_DB,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> list[dict]:
    """读 session.db，取窗口内所有会话的对话原文（含角色）。

    Returns:
        [{"role": "user"|"model", "author": str, "text": str}, ...] 按时间升序
    """
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - window_minutes * 60
        rows = conn.execute(
            "SELECT session_id, timestamp, event_data FROM events WHERE timestamp >= ? ORDER BY timestamp",
            (cutoff,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []

    msgs = []
    for sid, ts, event_data in rows:
        try:
            ev = json.loads(event_data)
        except json.JSONDecodeError:
            continue
        role = (ev.get("content") or {}).get("role", "")
        if role not in ("user", "model"):
            continue
        text = _extract_text(event_data)
        if not text:
            continue
        author = ev.get("author", "")  # author 在 event_data 里，不在 SQL 列
        msgs.append({"role": role, "author": author, "text": text, "timestamp": ts, "session_id": sid})
    return msgs[-max_messages:]  # 只保留最近 N 条


def build_stm_context(
    db_path: Path = SESSION_DB,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> str | None:
    """构建注入 prompt 的短期记忆文本块。窗口内无消息 → 返回 None（不注入）。

    输出形如：
    [系统短期记忆]（最近 20 分钟的对话，供理解当前语境）
    user: 我想投债券承做方向
    model: 好的，这是国信证券债承 JD 的分析报告…
    """
    msgs = read_recent_messages(db_path, window_minutes, max_messages)
    if not msgs:
        return None
    lines = [f"[系统短期记忆]（最近 {window_minutes} 分钟内，共 {len(msgs)} 条）"]
    for m in msgs:
        tag = "user" if m["role"] == "user" else "assistant"
        text = m["text"].replace("\n", " ")[:200]
        lines.append(f"- {tag}: {text}")
    return "\n".join(lines)


def save_stm_context(text: str | None, db_path: Path = SESSION_DB,
                     window_minutes: int = DEFAULT_WINDOW_MINUTES) -> None:
    """把当前 STM 上下文落盘到 stm_ctx.json（供排查 / 后续压缩复用）。"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "window_minutes": window_minutes,
        "db": str(db_path),
        "messages": read_recent_messages(db_path, window_minutes),
        "context_text": text,
    }
    STM_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import sys as _sys

    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ctx = build_stm_context()
    save_stm_context(ctx)
    print(ctx or "(窗口内无对话，无 STM)")
