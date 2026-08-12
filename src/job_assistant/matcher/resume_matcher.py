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


MATCH_PROMPT = """你是一名深耕财经求职领域多年的专业顾问，对券商投行、行研、PE/VC、基金资管、银行、四大审计等各细分赛道的工作内容、技能栈、行业术语和简历惯例有深入理解。根据岗位需求、候选人画像、硬门槛校验结果、检索到的高分案例，做证据化的差距分析。只输出一个 JSON 对象：

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
  "top_suggestions": ["按优先级排序的简历修改建议，3到5条，每条2到4句话"],
  "sources": ["分析中实际引用过的案例 source，按如下格式：role_name @company (source=xxx)"]
}

规则（防幻觉，务必遵守）：
- 每条差距必须有 evidence 依据；画像和案例里都找不到依据的，needs_proof 必须为 true，
  并在 suggestion 里写明需要补充什么证据。
- 硬门槛校验里 fail 的项必须反映在 gaps 和 verdict 里；unknown 的项 needs_proof=true。
- 只基于给定的输入分析，不要脑补画像里没有的信息。
- 不要凭空编造案例内容，引用案例必须用其 source。
- 分析差距（gaps）时只对标 JD 的「任职要求」段；「岗位职责」段里提到的行业/方向
  （如半导体、量子计算）描述的是入职后的学习范围，不是候选人当前必须掌握的领域，
  不要据此判定"不匹配"。
- top_suggestions 必须体现财经行业专业性，不能浮于表面（这是核心要求，务必遵守）：
  * 结合岗位所属赛道（role_category）的行业知识与岗位职责，用专业术语给出具体建议。
    例如：投行岗 → 结合 IPO/并购重组/尽职调查/财务建模（DCF、可比公司估值）/募集说明书/底稿等；
    行研岗 → 结合深度报告/盈利预测/估值模型/晨会/路演/数据底稿（Wind、Bloomberg）等；
    PE/VC/资管 → 结合尽调/估值建模/LBO/投后管理/退出机制/一二级市场联动等；
    银行/四大 → 结合信贷尽调/审计底稿/内控测试/科目分析等。
  * 参考检索到的高分案例原文的简历写法（成功上岸者的背景/实习描述/项目成果是最好的范本），
    吸收其中的措辞、结构、量化方式，但**不要写"参考了XX案例"**这类话，直接给具体建议即可。
  * 每条建议写清：改简历哪个字段/段落 → 用什么专业措辞或行业标准写法 → 对标岗位哪个具体要求的哪一点、为什么这样改。
  * 每条 3~5 句，不要只写一句方向性的话，一定要落到可操作的层面（给出建议的具体措辞或数据表述）。
  * 主动利用 JD「岗位职责」里的行业/赛道信息：若职责提到半导体/电子/量子计算/新能源等方向，
    建议候选人提前阅读该行业的深度报告、学习产业链知识、了解主要公司和竞争格局，
    甚至建议在简历里加一个"行业研究/追踪"栏目体现主动性——职责里的行业方向就是最好的提前准备指南。
- gaps 里每条 gap 的 suggestion 同样要结合行业术语，与 top_suggestions 的专业水准保持一致。
- 遇到时间出勤、软性素质这类已归并的条目，gaps 里也只出一项，不要内部再拆开。
  整体判断是否吻合（如"出勤要求总体吻合/不吻合"），suggestion 一并给出，不逐项列。
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
    # 把案例原文一并传给 LLM，让它能基于具体 bg/学历/技能/结果做差距分析，
    # 而不是只看一行摘要（否则 LLM 无内容可引用，差距分析和建议都会空泛）。
    case_lines = []
    for c in retrieval.cases:
        case_lines.append(
            f"- [{c.role_category}] {c.role_name} @{c.company} 相似度{c.score} source={c.source}\n"
            f"  案例原文：\n{c.content}"
        )
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
