"""长期记忆每日摘要 CLI：对某天对话做摘要，归入三类 MD 文件。

用法：
    python scripts/run_memory_digest.py            # 摘要今天
    python scripts/run_memory_digest.py --day 2026-08-07   # 摘要指定日期
    python scripts/run_memory_digest.py --dry-run  # 只预览不写盘
    python scripts/run_memory_digest.py --history  # 查看可用的历史事件日期
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.memory import ltm  # noqa: E402
from job_assistant.paths import SESSION_DB  # noqa: E402


def _available_days(db_path) -> list[str]:
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT DISTINCT datetime(timestamp,'unixepoch','localtime') FROM events ORDER BY 1"
    ).fetchall()
    conn.close()
    # 只保留日期部分并去重（同一天多条事件）
    return sorted({r[0][:10] for r in rows})


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    if "--history" in args:
        days = _available_days(SESSION_DB)
        print("可用历史事件日期：")
        for d in days:
            print(" ", d)
        return

    day = None
    if "--day" in args:
        day = args[args.index("--day") + 1]

    dry_run = "--dry-run" in args
    print(f"== 长期记忆摘要（{day or '今天'}）{'—— 仅预览' if dry_run else ''} ==")
    result = ltm.digest_day(day=day, write=not dry_run)

    if "skipped" in result:
        print(result["skipped"])
        return

    print(json.dumps(
        {
            "消息数": result["messages"],
            "用户画像": result["user_profile"],
            "助手设定": result["agent_setting"],
            "长期经历": result["dream"],
        },
        ensure_ascii=False, indent=2,
    ))
    if not dry_run:
        print("\n已写入 data/memory/ 下三个 MD 文件。")
        for f in (ltm.MD_FILES["user_profile"], ltm.MD_FILES["agent_setting"], ltm.MD_FILES["dream"]):
            print(f"  {f}")


if __name__ == "__main__":
    main()
