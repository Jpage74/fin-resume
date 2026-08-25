"""冒烟：reviewer 双层复核 —— 代码硬规则拦截真违规 + 不再误报「未引用 source」。

验证三件事：
  1. 真违规必拦（纯代码层，确定性）：无证据下结论 / fail 却建议投递 / 编造 source
  2. 历史误报场景不再触发：检索返回多条、报告只引用部分 → 合规放行
  3. 端到端（含 LLM 语义层）：合规报告 approved=True，且 LLM 不重复报硬规则
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.analyzer.rules import GateStatus  # noqa: E402
from job_assistant.matcher.resume_matcher import GapItem, MatchReport  # noqa: E402
from job_assistant.reviewer.reviewer import code_check, review  # noqa: E402


def _gap(**kw) -> GapItem:
    base = dict(requirement="熟练使用 Excel", status="satisfied", gap_description="匹配",
                evidence="画像 skills 含 Excel", needs_proof=False, suggestion="")
    base.update(kw)
    return GapItem(**base)


def main() -> int:
    # 检索元数据是「裸 source」；matcher 引用是「role @company (source=xxx)」装饰格式
    raw_sources = ["公开校招分享/示例-001", "牛客/bg帖-用户提供-002"]
    gates_ok = [{"requirement": {"description": "硕士", "evidence_key": "degree>=硕士"},
                 "status": GateStatus.PASS.value, "reason": "满足"}]

    print("=== 1) 真违规必拦（code_check，确定性，不依赖 LLM） ===")
    bad = MatchReport(
        match_score=90, verdict="建议投递",
        gaps=[_gap(evidence="", needs_proof=False)],  # 违规1：无证据下结论
        strengths=[], top_suggestions=[], sources=["编造的source"],  # 违规3：编造来源
    )
    ctx_bad = {
        "gates": [{"requirement": {"description": "硕士", "evidence_key": "degree>=硕士"},
                   "status": GateStatus.FAIL.value, "reason": "不满足"}],  # 违规2：fail 却建议投递
        "retrieval_sources": raw_sources,
        "profile": {"user": {}},
    }
    findings, corrections, hard_ok, verdict_sound = code_check(bad, ctx_bad)
    items = [f.item for f in findings]
    assert not hard_ok, "真违规未被拦截"
    assert any(i.startswith("gap:") for i in items), f"规则1未拦截: {items}"
    assert any(i == "verdict" for i in items), f"规则2未拦截: {items}"
    assert any(i.startswith("source:") for i in items), f"规则3未拦截: {items}"
    assert verdict_sound is False
    print(f"  拦截 {len(findings)} 项 error：{items}")

    print("\n=== 1b) 检索为空却引用 source → 也拦 ===")
    f1b, _, ok1b, _ = code_check(
        MatchReport(match_score=50, verdict="不建议投递", gaps=[], strengths=[],
                    top_suggestions=[], sources=["凭空来源"]),
        {"gates": [], "retrieval_sources": [], "profile": {}},
    )
    assert not ok1b and any(i.startswith("source:") for i in (x.item for x in f1b)), "空检索引用未被拦"
    print("  拦截 OK")

    print("\n=== 2) 历史误报场景不再触发（部分引用 + 装饰格式 = 合规） ===")
    good = MatchReport(
        match_score=75, verdict="谨慎投递",
        gaps=[
            _gap(),
            _gap(requirement="有行研实习经历者优先", status="unknown", gap_description="待确认",
                 evidence="", needs_proof=True),  # 无证据但标了 needs_proof → 合规
        ],
        strengths=["硕士学历满足硬门槛"],
        top_suggestions=["实习经历用行研术语量化"],
        sources=["行业研究实习生 @华泰证券研究所 (source=公开校招分享/示例-001)"],  # 装饰格式、只引 1/2 条 → 合规
    )
    ctx_good = {"gates": gates_ok, "retrieval_sources": raw_sources, "profile": {"user": {"degree": "硕士"}}}
    findings2, _, hard_ok2, vs2 = code_check(good, ctx_good)
    assert hard_ok2, f"误报未消除: {[f.issue for f in findings2]}"
    assert vs2 is True
    print("  code_check 通过：0 findings，verdict_sound=True（历史误报已消除）")

    print("\n=== 3) 端到端 review()（含 LLM 语义层） ===")
    result = review(good, ctx_good)
    errs = [f for f in result.findings if f.severity == "error"]
    print(f"  approved={result.approved}  verdict_sound={result.verdict_sound}")
    for f in result.findings:
        print(f"    [{f.severity}] {f.item}: {f.issue[:60]}")
    assert result.approved, f"合规报告被拦截: {[f.issue for f in errs]}"
    assert not errs, f"LLM 仍在报硬规则/误报: {[f.issue for f in errs]}"

    print("\nsmoke_reviewer: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
