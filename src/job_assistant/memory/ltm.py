"""长期记忆（LTM）：每日对当天对话做摘要，归入三类 MD 文件。

设计（设计文档五、用户确认）：
- 每天运行一次摘要，数据源是 ADK session.db 当天产生的 events
- LLM 把当天对话摘要按 3 个维度拆开输出：
    user_profile_updates   → user_profile.md   用户画像类（能力/目标/短板/进展）
    agent_setting_updates  → agent_setting.md  行为偏好类（风格/强调/忽略）
    dream_updates          → dream.md          经历类（发生了什么/决策/发现）
- 各维度内容按「## YYYY-MM-DD」节 APPEND 到对应 MD，不覆盖历史
- 注入：会话启动时读取最近若干天的 MD 内容注入 prompt

存储：data/memory/{user_profile,agent_setting,dream}.md（gitignore 排除）
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from job_assistant.llm import complete_json  # noqa: E402
from job_assistant.paths import MEMORY_DIR, SESSION_DB  # noqa: E402

load_dotenv()

MD_FILES = {
    "user_profile": MEMORY_DIR / "user_profile.md",
    "agent_setting": MEMORY_DIR / "agent_setting.md",
    "dream": MEMORY_DIR / "dream.md",
}

DIGEST_PROMPT = """你是一名求职私人助理的记忆整理员。把用户今天与「财经求职助手」的对话整理成长期记忆，只输出一个 JSON 对象，三个字段：

{
  "user_profile_updates": ["画像类记忆，如：用户目标是XX方向、某证书是短板、投递了哪家公司、求职进展等"],
  "agent_setting_updates": ["行为偏好类记忆，如：用户希望回答更简洁、对'待证据'标记很在意、强调不要编造等"],
  "dream_updates": ["经历类记忆，如：今天分析了哪几份JD、做了哪些对比决策、发现了什么信息、用户表达了什么倾向"]
}

规则：
- 每个字段是字符串数组，每项一句话，宁缺毋滥；没有对应内容就空数组 []。
- 只基于对话中真实出现的信息，不要脑补。
- 对话中的敏感个人信息（姓名、联系方式）不要写入，写"用户"。
- 只输出 JSON，不要多余文字。"""


def _read_day_events(db_path: Path, day: str | None = None) -> list[dict]:
    """读 session.db 某天的对话文本（day=YYYY-MM-DD，默认今天）。"""
    if not db_path.exists():
        return []
    if day is None:
        day = datetime.now().astimezone().strftime("%Y-%m-%d")
    try:
        # 该天零点 / 次日零点（本地时区 → UTC 时间戳）
        dt_local = datetime.strptime(day, "%Y-%m-%d").astimezone()
        start_utc = dt_local.astimezone(timezone.utc).timestamp()
        end_utc = start_utc + 86400
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT session_id, timestamp, event_data FROM events"
            " WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (start_utc, end_utc),
        ).fetchall()
        conn.close()
    except (sqlite3.Error, ValueError):
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
        parts = (ev.get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if "text" in p]
        text = "\n".join(texts).strip()
        if not text:
            continue
        author = ev.get("author", "")
        msgs.append({"role": role, "author": author, "session_id": sid, "text": text})
    return msgs


def _conversation_text(msgs: list[dict]) -> str:
    """消息 → 摘要输入文本（限制长度防超 token）。"""
    lines = []
    for m in msgs:
        tag = "用户" if m["role"] == "user" else "助手"
        text = m["text"].strip()
        if not text:
            continue
        # 截断超长单条（如完整简历），保留开头摘要能力足够
        lines.append(f"{tag}: {text[:500]}")
    blob = "\n\n".join(lines)
    # 总输入限制 12000 字符
    return blob[-12000:]


def digest_day(day: str | None = None, db_path: Path = SESSION_DB, write: bool = True) -> dict:
    """对某天对话做摘要，写回三类 MD。返回摘要 dict。

    Args:
        day: YYYY-MM-DD，默认今天。
        write: False 则不落盘，仅返回摘要（dry-run）。
    """
    msgs = _read_day_events(db_path, day)
    if not msgs:
        return {"day": day or datetime.now().astimezone().strftime("%Y-%m-%d"),
                "messages": 0, "skipped": "当天无对话"}

    data = complete_json(
        messages=[
            {"role": "system", "content": DIGEST_PROMPT},
            {"role": "user", "content": f"=== 今天（{day}）的对话 ===\n{_conversation_text(msgs)}\n=== 结束 ==="},
        ],
    )
    result = {
        "day": day or datetime.now().astimezone().strftime("%Y-%m-%d"),
        "messages": len(msgs),
        "user_profile": data.get("user_profile_updates") or [],
        "agent_setting": data.get("agent_setting_updates") or [],
        "dream": data.get("dream_updates") or [],
    }
    if write:
        for key, entries in (("user_profile", result["user_profile"]),
                             ("agent_setting", result["agent_setting"]),
                             ("dream", result["dream"])):
            if entries:
                _append_to_md(MD_FILES[key], result["day"], entries)
    return result


def _append_to_md(path: Path, day: str, entries: list[str]) -> None:
    """往 MD 追加「## 日期」节（不覆盖历史）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    block = [f"\n## {day}", ""]
    block += [f"- {e}" for e in entries]
    block.append("")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(block))


def load_recent_md(limit_days: int = 3) -> str:
    """读取最近 N 天的三类 MD 摘要，拼接成注入 prompt 的长期记忆块。

    简单实现：各取文件最近若干行（按 ## 日期 分节），MVP 足够。
    """
    parts = []
    for label, path in (("用户画像", MD_FILES["user_profile"]),
                        ("助手设定", MD_FILES["agent_setting"]),
                        ("长期经历", MD_FILES["dream"])):
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        parts.append(f"[{label}]\n{content}")
    if not parts:
        return ""
    return "[系统长期记忆]\n" + "\n\n".join(parts)


if __name__ == "__main__":
    import sys as _sys

    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # 默认摘要今天；无则显示可用历史天数
    if len(_sys.argv) > 1 and _sys.argv[1] == "--history":
        import sqlite3 as _sq

        conn = _sq.connect(str(SESSION_DB))
        rows = conn.execute("SELECT DISTINCT datetime(timestamp,'unixepoch','localtime') FROM events").fetchall()
        conn.close()
        print("历史事件时间:", rows[:10])
    else:
        result = digest_day()
        print(json.dumps(result, ensure_ascii=False, indent=2))
