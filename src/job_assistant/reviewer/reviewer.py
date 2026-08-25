"""复核子 agent：对主链路输出做交叉检查，纠错 + 放行/拦截。

管线的防幻觉硬门（第四环）。设计原则「约束外包」（设计文档八）：
关键判断不信任 LLM 的自由解释——三条硬规则由**纯代码确定性校验**，
LLM 只负责需要语义理解的越界检查。这样即使 LLM 输出漂移，硬规则也必然执行。

代码校验的硬规则（缺一即 error，approved=False）：
1. 证据绑定：每条 gap 必须有 evidence，或 needs_proof=true
2. verdict 一致性：硬门槛有 fail 不得判「建议投递」
3. 来源真实：引用的 source 必须存在于检索结果里（编造来源 = 幻觉）

注意：检索结果里有 source 未被报告引用**不是**问题（检索返回多条、报告择要引用），
历史上 LLM 曾把它误读成违规导致误报拦截，故此判断已完全收归代码。
"""
from __future__ import annotations

import json
import re
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


REVIEW_PROMPT = """你是一名招聘流程质检员，负责对求职匹配报告做**语义越界检查**。

重要：以下三类检查已由系统代码确定性完成并强制执行，你不需要、也不应该重复报告：
- gap 无证据也未标 needs_proof（证据绑定）
- 硬门槛有 fail 却判「建议投递」（verdict 一致性）
- 引用了检索结果里不存在的 source（编造来源）

你的唯一职责（规则4 · 语义核查）：
strengths / top_suggestions / 各条 gap_description：若引用了用户画像或案例中不存在的内容
（虚构的经历、证书、技能、数据或案例细节）→ error；都能在画像或案例里找到依据 → 合规，不要报。

明确不属于问题的情形（绝对不要报告）：
- 检索结果里有 source 未被报告引用 —— 正常现象（检索返回多条，报告择要引用），不是遗漏更不是错误。
- gap 的 evidence 为空但 needs_proof=true —— 合规。
- 硬门槛有 fail 而 verdict 不是「建议投递」 —— 合规。

只输出一个 JSON 对象：
{
  "approved": true或false,
  "verdict_sound": true,
  "findings": [
    {"item": "问题对应项", "severity": "error或warning或info", "issue": "问题描述"}
  ],
  "corrections": ["具体修正建议"]
}

严重度含义：error=引用了不存在的内容（语义幻觉）；warning=可疑但不违反规则；info=备注。
没有问题就不要写 findings，不要凑数，拿不准给 info，绝不夸大。只输出 JSON，不要多余文字。"""


def _extract_source_key(cited: str) -> str:
    """从引用串提取裸 source：「role @company (source=xxx)」→ xxx；无装饰则原样返回。"""
    text = (cited or "").strip()
    m = re.search(r"source\s*=\s*([^（）)]+)[）)]?\s*$", text)
    return (m.group(1) if m else text).strip()


def code_check(report, context: dict) -> tuple[list[ReviewFinding], list[str], bool, bool]:
    """确定性硬规则校验（不依赖 LLM）。

    Returns:
        (findings, corrections, hard_ok, verdict_sound)
        hard_ok=False 表示存在 error 级违规，approved 必须为 False。
    """
    findings: list[ReviewFinding] = []
    corrections: list[str] = []

    # 规则1 证据绑定：gap 无 evidence 且未标 needs_proof → 幻觉
    for g in report.gaps:
        if not (g.evidence or "").strip() and not g.needs_proof:
            findings.append(
                ReviewFinding(
                    item=f"gap:{g.requirement}",
                    severity="error",
                    issue="无证据却下了结论（既无 evidence 也未标 needs_proof），属幻觉",
                )
            )
            corrections.append(f"为『{g.requirement}』补充 evidence，或将 needs_proof 置 true")

    # 规则2 verdict 一致性：硬门槛有 fail 不得判「建议投递」
    fails = [g for g in context.get("gates", []) if g.get("status") == GateStatus.FAIL.value]
    verdict_sound = not (fails and report.verdict == "建议投递")
    if not verdict_sound:
        findings.append(
            ReviewFinding(
                item="verdict",
                severity="error",
                issue=f"硬门槛存在 {len(fails)} 项 fail，但 verdict 为『建议投递』",
            )
        )
        corrections.append("硬门槛存在未满足项时，verdict 应下调为『谨慎投递』或『不建议投递』")

    # 规则3 来源真实：引用的 source 必须存在于检索结果（单向核对；
    # 检索结果未被全部引用是正常的，不在此列——这是历史误报的根源，已收归代码）。
    # matcher 引用是装饰格式「role @company (source=xxx)」，需提取裸 source 再比对。
    valid_sources = set(context.get("retrieval_sources", []) or [])
    for s in report.sources:
        key = _extract_source_key(s)
        if not key or key in valid_sources:
            continue
        findings.append(
            ReviewFinding(item=f"source:{s}", severity="error", issue="引用了检索结果中不存在的 source（编造来源）")
        )
        corrections.append(f"删除或修正编造的 source：{s}")

    hard_ok = not findings
    return findings, corrections, hard_ok, verdict_sound


def review(
    report,
    context: dict,
    model: str = DEFAULT_MODEL,
) -> ReviewResult:
    """复核 MatchReport：代码硬规则 + LLM 语义检查，双层合并。

    Args:
        report: resume_matcher 输出的 MatchReport。
        context: 复核所需的事实底座，建议包含：
            {"gates": [...], "retrieval_sources": [...], "profile": {...}}
    """
    # 第一层：代码确定性校验（必然执行，不可被 LLM 忽视）
    code_findings, code_corrections, hard_ok, verdict_sound = code_check(report, context)

    # 第二层：LLM 语义检查（仅规则4：strengths/suggestions 是否引用不存在内容）
    payload = {
        "MatchReport": json.loads(report.model_dump_json()),
        "用户画像": context.get("profile", {}),
        "检索结果的 source 列表": context.get("retrieval_sources", []),
    }
    llm_findings: list[ReviewFinding] = []
    llm_corrections: list[str] = []
    try:
        data = complete_json(
            model=model,
            messages=[
                {"role": "system", "content": REVIEW_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
            ],
        )
        llm = ReviewResult.model_validate(data)
        llm_findings = llm.findings
        llm_corrections = llm.corrections
        llm_has_error = any(f.severity == "error" for f in llm_findings)
    except Exception as e:  # noqa: BLE001
        # LLM 层失败不阻塞：硬规则已由代码兜底，标注 info 说明语义检查未完成
        llm_findings = [
            ReviewFinding(item="reviewer-llm", severity="info", issue=f"语义检查未完成：{type(e).__name__}: {e}")
        ]
        llm_has_error = False

    approved = hard_ok and not llm_has_error
    return ReviewResult(
        approved=approved,
        verdict_sound=verdict_sound,
        findings=[*code_findings, *llm_findings],
        corrections=[*code_corrections, *llm_corrections],
    )


if __name__ == "__main__":
    # 冒烟：故意违规的最小报告 → 三条硬规则都应由代码层拦下
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
        sources=["编造的source"],  # 故意违规：编造来源
    )
    ctx = {
        "gates": [
            {
                "requirement": {"description": "硕士学历", "evidence_key": "degree>=硕士"},
                "status": GateStatus.FAIL.value,  # 故意违规：fail 却建议投递
                "reason": "画像无学历记录",
            }
        ],
        "retrieval_sources": [],
        "profile": {"user": {}},
    }
    r = review(mini, ctx)
    print(r.model_dump_json(indent=2, ensure_ascii=False))
