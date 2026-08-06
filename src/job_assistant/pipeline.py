"""核心闭环编排：JD → 完整四环管线 → 结果。

设计文档「MVP 核心闭环」：
    输入 JD → jd_analyzer 抽需求（硬门槛规则校验）
            → case_retriever 检索匹配岗位 + 高分案例
            → resume_matcher 证据化差距分析（needs_proof）
            → reviewer 复核（防幻觉硬门）

本模块把四环串成单个 run_pipeline，CLI / adk agent / 未来的 web 都能复用它。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from job_assistant.analyzer.jd_analyzer import analyze_jd  # noqa: E402
from job_assistant.analyzer.rules import GateResult, validate_hard_gates  # noqa: E402
from job_assistant.matcher.resume_matcher import MatchReport, match  # noqa: E402
from job_assistant.memory.profile import load_profile  # noqa: E402
from job_assistant.retriever.case_retriever import CaseRetriever, RetrievalResult  # noqa: E402
from job_assistant.retriever.seed import build_index  # noqa: E402
from job_assistant.reviewer.reviewer import ReviewResult, review  # noqa: E402
from job_assistant.schemas import JobRequirements  # noqa: E402


@dataclass
class PipelineResult:
    """一次完整分析的所有中间产物，供 CLI / web / agent 展示与落库。"""

    reqs: JobRequirements
    gates: list[GateResult]
    retrieval: RetrievalResult
    report: MatchReport
    review_result: ReviewResult
    profile: dict = field(default_factory=dict)


def run_pipeline(
    jd_text: str,
    source: str = "",
    seed_index: bool = False,
    profile_path: Path | None = None,
) -> PipelineResult:
    """跑完整四环管线。

    Args:
        jd_text: 岗位 JD 原文。
        source: JD 来源标识（渠道+编号），用于溯源与历史去重。
        seed_index: True 则先全量重建向量索引（知识库变更后需开）。
        profile_path: 用户画像路径，默认 data/profile.yaml。
    """
    profile = load_profile(profile_path) if profile_path else load_profile()

    # ① 解析
    reqs = analyze_jd(jd_text, source=source)
    # ② 硬门槛 + 检索
    retriever = CaseRetriever()
    if seed_index:
        build_index(retriever, verbose=True)
    gates = validate_hard_gates(reqs, profile)
    retrieval = retriever.retrieve(reqs)
    # ③ 差距分析
    report = match(reqs, profile, retrieval, gates=gates)
    # ④ 复核
    review_result = review(
        report,
        context={
            "gates": [
                {"requirement": g.requirement.description, "evidence_key": g.requirement.evidence_key, "status": g.status.value, "reason": g.reason}
                for g in gates
            ],
            "retrieval_sources": [c.source for c in retrieval.cases] + [j.source for j in retrieval.jds],
            "profile": profile,
        },
    )
    return PipelineResult(
        reqs=reqs, gates=gates, retrieval=retrieval,
        report=report, review_result=review_result, profile=profile,
    )


def needs_proof_items(report: MatchReport) -> list[str]:
    """缺证据的需求描述列表（历史落库用）。"""
    return [g.requirement for g in report.gaps if g.needs_proof]
