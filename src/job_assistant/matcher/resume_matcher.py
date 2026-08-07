"""差距分析子 agent：JobRequirements × 用户画像 × 检索案例 → 证据化匹配报告。

管线第三环。输入三样东西：
- JobRequirements（jd_analyzer 输出）
- 用户画像（memory/profile）
- 硬门槛校验结果 + 检索到的匹配岗位/上岸背景画像（rules + case_retriever）

输出 MatchReport：逐条差距分析（每条绑定证据 / 无证据标 needs_proof）、
匹配度评分、判定、按优先级的简历修改建议。

防幻觉约定（设计文档六）：每个结论必须可溯源；画像与案例里都找不到依据的，
needs_proof=True，建议里写明缺什么证据，不编造。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from job_assistant.analyzer.rules import GateResult, validate_hard_gates  # noqa: E402
from job_assistant.llm import DEFAULT_MODEL, complete_json  # noqa: E402
from job_assistant.retriever.case_retriever import RetrievalResult  # noqa: E402
from job_assistant.schemas import JobRequirements  # noqa: E402

load_dotenv()


class GapItem(BaseModel):
    requirement: str = Field(description="需求描述")
    status: str = Field(description="satisfied / gap / unknown")
    gap_description: str = Field(description="差距说明")
    evidence: str = Field(description="判定依据（画像字段/证书/技能/案例 source），无则空串")
    needs_proof: bool = Field(default=False, description="无证据支撑时必须为 true")
    suggestion: str = Field(description="具体可操作的简历修改建议")


class MatchReport(BaseModel):
    match_score: int = Field(ge=0, le=100, description="综合匹配度 0~100")
    verdict: str = Field(description="建议投递 / 谨慎投递 / 不建议投递")
    gaps: list[GapItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list, description="画像相对该岗位的亮点")
    top_suggestions: list[str] = Field(default_factory=list, description="按优先级排序的简历修改建议 3~5 条")
    sources: list[str] = Field(default_factory=list, description="引用过的案例 source")


MATCH_PROMPT = """你是一名资深财经招聘顾问。根据岗位需求、候选人画像、硬门槛校验结果、检索到的高分案例，做证据化的差距分析。只输出一个 JSON 对象：

{
  "match_score": 0到100整数，综合匹配度,
  "verdict": "建议投递 / 谨慎投递 / 不建议投递 之一",
  "gaps": [
    {
      "requirement": "需求描述（原样引用）",
      "status": "satisfied / gap / unknown 之一",
      "gap_description": "差距说明",
      "evidence": "判定依据：画像里的字段/证书/技能，或案例 source；没有就空串",
      "needs_proof": true或false,
      "suggestion": "具体可操作的简历修改建议"
    }
  ],
  "strengths": ["画像相对该岗位的亮点，逐条"],
  "top_suggestions": ["按优先级排序的简历修改建议，3到5条"],
  "sources": ["分析中实际引用过的案例 source，按如下格式：role_name @company (source=xxx)"]
}

规则（防幻觉，务必遵守）：
- 每条差距必须有 evidence 依据；画像和案例里都找不到依据的，needs_proof 必须为 true，
  并在 suggestion 里写明需要补充什么证据。
- 硬门槛校验里 fail 的项必须反映在 gaps 和 verdict 里；unknown 的项 needs_proof=true。
- 只基于给定的输入分析，不要脑补画像里没有的信息。
- 不要凭空编造案例内容，引用案例必须用其 source。
- 只输出 JSON，不要多余文字。"""


def match(
    reqs: JobRequirements,
    profile: dict,
    retrieval: RetrievalResult,
    gates: list[GateResult] | None = None,
    model: str = DEFAULT_MODEL,
) -> MatchReport:
    """输入标准化需求 + 画像 + 检索结果 → 证据化匹配报告。"""
    if gates is None:
        gates = validate_hard_gates(reqs, profile)

    gate_lines = [
        f"- [{g.status.value}] {g.requirement.description}（evidence_key={g.requirement.evidence_key}）{g.reason}"
        for g in gates
    ]
    case_lines = [
        f"- [{c.role_category}] {c.role_name} @{c.company} 相似度{c.score} source={c.source}"
        for c in retrieval.cases
    ]
    jd_lines = [
        f"- [{jd.role_category}] {jd.role_name} @{jd.company} 相似度{jd.score} source={jd.source}"
        for jd in retrieval.jds
    ]

    context = "\n".join(
        [
            "===== 岗位需求（JobRequirements） =====",
            json.dumps(json.loads(reqs.model_dump_json()), ensure_ascii=False, indent=1),
            "===== 候选人画像（profile） =====",
            json.dumps(profile, ensure_ascii=False, indent=1),
            "===== 硬门槛校验结果 =====",
            "\n".join(gate_lines) or "(无硬门槛)",
            "===== 匹配岗位（检索） =====",
            "\n".join(jd_lines) or "(无)",
            "===== 高分案例（检索） =====",
            "\n".join(case_lines) or "(无)",
        ]
    )
    messages = [
        {"role": "system", "content": MATCH_PROMPT},
        {"role": "user", "content": context},
    ]
    data = complete_json(model=model, messages=messages)
    return MatchReport.model_validate(data)


if __name__ == "__main__":
    # 冒烟：解析 JD → 检索 → 差距分析
    from job_assistant.analyzer.jd_analyzer import analyze_jd
    from job_assistant.memory.profile import load_profile
    from job_assistant.retriever.case_retriever import CaseRetriever
    from job_assistant.retriever.seed import build_index

    sample = """公司：华泰证券研究所
岗位：行业研究实习生（消费方向）
【学历要求】重点院校硕士在读，2027 届优先；
【技能要求】熟练使用 Excel、Wind，掌握 Python 或 R 者加分；
【实习要求】有券商研究所实习经历者优先；"""
    reqs = analyze_jd(sample, source="smoke:华泰行研实习")
    retriever = CaseRetriever()
    build_index(retriever, verbose=False)
    result = retriever.retrieve(reqs)
    report = match(reqs, load_profile(), result)
    print(report.model_dump_json(indent=2, ensure_ascii=False))
