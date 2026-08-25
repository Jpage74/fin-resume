"""冒烟：反馈回路 —— feedback 落库/查询/统计 + record_feedback 工具胶水。

不污染真实 data/history.db：数据层用临时 db_path；工具层用桩函数替换 add_feedback。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agents"))

from job_assistant.memory.history import add_feedback, feedback_stats, list_feedback  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_feedback_")) / "history.db"

    print("=== 1) 数据层：落库 / 查询 / 统计（临时 db） ===")
    for rating, comment in [("有用", ""), ("不准", "匹配分偏高，实习证据没对上"), ("有用", "案例引用很实在")]:
        add_feedback(
            rating, comment,
            role_category="券商行研", company="华泰证券", role_name="行业研究实习生",
            match_score=72, verdict="谨慎投递", db_path=tmp,
        )
    rows = list_feedback(db_path=tmp)
    assert len(rows) == 3 and rows[0][3] == "有用", f"list_feedback 异常: {rows}"
    stats = feedback_stats(db_path=tmp)
    assert stats == {"total": 3, "useful": 2, "inaccurate": 1, "inaccurate_rate": 0.3333}, stats
    print(f"  3 条反馈：{stats}")
    print(f"  最新一条：{rows[0]}")

    print("\n=== 2) 工具层：record_feedback（桩替换 add_feedback，不动真实库） ===")
    import fin_resume.tools as T  # noqa: E402

    captured: list[dict] = []
    orig = T.add_feedback
    T.add_feedback = lambda **kw: captured.append(kw)
    try:
        bad = T.record_feedback("还行吧")
        n_after_bad = len(captured)
        ok = T.record_feedback("不准", "差距分析没提到 CPA 短板")
    finally:
        T.add_feedback = orig
    assert "只能" in bad and n_after_bad == 0, f"非法 rating 未被正确拒绝: {bad}"
    assert len(captured) == 1, "合法反馈未被捕获"
    kw = captured[0]
    assert kw["rating"] == "不准" and "CPA" in kw["comment"], kw
    print(f"  非法 rating 拒绝：{bad[:24]}…")
    print(f"  合法反馈捕获：rating={kw['rating']} comment={kw['comment']!r}")

    print("\nsmoke_feedback: PASS（临时目录可删：" + str(tmp.parent) + "）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
