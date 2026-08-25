"""冒烟：role_profiler 岗位画像器 —— 只给岗位名 → 聚合典型要求 → JobRequirements。

验证：
  1. classify_role 确定性别名命中（不发 LLM）
  2. profile_role 产出合法 JobRequirements，role_category 对齐、evidence_key 落受控词表
  3. run_pipeline_reqs 能消费 role_profiler 的产物跑完整后续管线（不影响原 run_pipeline 链路）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.analyzer.role_profiler import ROLE_CATEGORIES, classify_role, profile_role  # noqa: E402
from job_assistant.pipeline import run_pipeline_reqs  # noqa: E402
from job_assistant.schemas import EVIDENCE_KEYS  # noqa: E402


def main() -> int:
    print("=== 1) classify_role 确定性匹配（不发 LLM） ===")
    for name, expect in [
        ("行研实习生", "券商行研"),
        ("四大审计", "四大审计"),
        ("投行部债券承做", "券商投行"),
        ("银行总行管培生", "银行管培"),
        ("PE股权投资分析", "PE股权投资"),
        ("财务BP", "互联网财务"),
        ("精算师", "保险精算"),
    ]:
        got = classify_role(name)
        mark = "OK" if got == expect else f"UNEXPECTED(期望{expect})"
        print(f"  {name!r} -> {got}  [{mark}]")
        assert got == expect, f"{name} 分类错误"

    print("\n=== 2) profile_role 聚合典型要求 ===")
    reqs = profile_role("四大审计")
    print(f"  role_category={reqs.role_category} role_name={reqs.role_name}")
    print(f"  source={reqs.source}")
    print(f"  summary={reqs.summary}")
    assert reqs.role_category == "四大审计", "role_category 未对齐"
    assert reqs.hard_requirements, "没有硬门槛"
    bad_keys = [
        r.evidence_key for r in reqs.requirements
        if r.evidence_key and r.evidence_key not in EVIDENCE_KEYS
    ]
    assert not bad_keys, f"evidence_key 越界受控词表: {bad_keys}"
    print(f"  硬门槛 {len(reqs.hard_requirements)} 条，总要求 {len(reqs.requirements)} 条，evidence_key 全部合法")
    for r in reqs.hard_requirements:
        print(f"    [hard] {r.description}  ({r.evidence_key})")

    print("\n=== 3) run_pipeline_reqs 跑完整后续管线 ===")
    result = run_pipeline_reqs(reqs)
    print(f"  硬门槛判定 {len(result.gates)} 项；匹配分 {result.report.match_score}/100 → {result.report.verdict}")
    print(f"  检索：岗位 {len(result.retrieval.jds)} 条 / 案例 {len(result.retrieval.cases)} 条")
    print(f"  复核：{'通过' if result.review_result.approved else '拦截'}")
    print("role_profiler: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
