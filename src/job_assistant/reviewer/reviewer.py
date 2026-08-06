"""复核子 agent：对主链路输出做交叉检查，纠错 + 放行/拦截。

管线第四环。复核对象：resume_matcher 的 MatchReport。
检查点（防幻觉硬规则）：
- 每条 gap 必须有 evidence 依据，或 needs_proof=true —— 否则视为幻觉，报 error
- verdict 与硬门槛校验结果一致：有 fail 不得判「建议投递」
- 引用的 source 必须存在于检索结果里，不得编造
- match_score 与 gaps 数量/严重度大致匹配
复核不通过（有 error 级 finding）→ approved=False，主链路要修正后才能给用户。

防幻觉原则（设计文档六）：宁可低置信度拦截，也不给用户一个编造的结论。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from job_assistant.analyzer.rules import GateStatus  # noqa: E402
from job_assistant.llm import DEFAULT_MODEL, complete_json  # noqa: E402

load_dotenv()


class ReviewFinding(BaseModel):
    item: str = Field(description="问题对应项，如『gap:熟练使用Excel』")
    severity: str = Field(description="error / warning / info")
    issue: str = Field(description="问题描述")


class ReviewResult(BaseModel):
    approved: bool = Field(description="是否有 error 级问题；false 则主链路需修正")
    verdict_sound: bool = Field(description="verdict 是否与硬门槛校验一致")
    findings: list[ReviewFinding] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list, description="具体修正建议")


REVIEW_PROMPT = """你是一名严格的招聘流程质检员，负责复核求职助手输出的匹配报告，防止幻觉与错误结论。只输出一个 JSON 对象：

{
  "approved": true或false,
  "verdict_sound": true或false,
  "findings": [
    {"item": "问题对应项", "severity": "error或warning或info", "issue": "问题描述"}
  ],
  "corrections": ["具体修正建议"]
}

复核规则（逐条执行）：
1. 对每条 gap：若 evidence 为空且 needs_proof 不为 true → error（无证据却下结论，幻觉）。
2. verdict 一致性：硬门槛校验有 fail 项，verdict 不能是『建议投递』，否则 error。
   硬门槛校验有 unknown 项且数量多，verdict 不应过于肯定。
3. sources 里引用的每一条都必须能在给定检索结果中找到对应 source，否则 error（编造来源）。
4. strengths / top_suggestions 若引用了画像或案例中不存在的内容 → error。
5. 其余小问题标 warning / info。

- 只有 error 级问题才把 approved 置为 false。
- 不要无中生有地挑刺；拿不准的给 info。
- 只输出 JSON，不要多余文字。"""


def review(
    report,
    context: dict,
    model: str = DEFAULT_MODEL,
) -> ReviewResult:
    """复核 MatchReport。

    Args:
        report: resume_matcher 输出的 MatchReport。
        context: 复核所需的事实底座，建议包含：
            {"gates": [...], "retrieval_sources": [...], "profile": {...}}
    """
    payload = {
        "MatchReport": json.loads(report.model_dump_json()),
        "硬门槛校验结果": context.get("gates", []),
        "检索结果的 source 列表": context.get("retrieval_sources", []),
        "用户画像": context.get("profile", {}),
    }
    messages = [
        {"role": "system", "content": REVIEW_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
    ]
    data = complete_json(model=model, messages=messages)
    return ReviewResult.model_validate(data)


if __name__ == "__main__":
    # 冒烟：对空画像的最小报告跑一次复核
    from job_assistant.matcher.resume_matcher import GapItem, MatchReport

    mini = MatchReport(
        match_score=90,
        verdict="建议投递",
        gaps=[
            GapItem(
                requirement="硕士学历",
                status="gap",
                gap_description="学历不足",
                evidence="",
                needs_proof=False,  # 故意违规：无证据却下结论
                suggestion="补学历",
            )
        ],
        strengths=["s1"],
        top_suggestions=["t1"],
        sources=[],
    )
    ctx = {
        "gates": [
            {
                "requirement": {"description": "硕士学历", "evidence_key": "degree>=硕士"},
                "status": GateStatus.FAIL.value,
                "reason": "画像无学历记录",
            }
        ],
        "retrieval_sources": [],
        "profile": {"user": {}},
    }
    r = review(mini, ctx)
    print(r.model_dump_json(indent=2, ensure_ascii=False))
