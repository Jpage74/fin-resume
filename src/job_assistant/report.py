"""PipelineResult → 可读报告文本（CLI 与 web 智能体工具共用）。"""
from __future__ import annotations

from job_assistant.analyzer.rules import GateStatus
from job_assistant.pipeline import PipelineResult

_GATE_MARK = {GateStatus.PASS: "[通过]", GateStatus.FAIL: "[不满足]", GateStatus.UNKNOWN: "[待证据]"}


def format_report(r: PipelineResult) -> str:
    """把一次完整分析格式化成 markdown 报告字符串。"""
    reqs, report, rev = r.reqs, r.report, r.review_result
    L: list[str] = []

    L.append(f"## 求职助手分析报告 | {reqs.role_name} @ {reqs.company or '(未写明)'} [ {reqs.role_category} ]")
    L.append(f"- **摘要**：{reqs.summary}")
    L.append(f"- **来源**：{reqs.source or '(未标注)'}")

    L.append(f"\n### ① 硬门槛校验（{len(r.gates)} 项）")
    for g in r.gates:
        L.append(f"- {_GATE_MARK[g.status]} **{g.requirement.description}** — {g.reason}")

    L.append("\n### ② 匹配岗位 & 上岸背景画像")
    if r.retrieval.jds:
        for jd in r.retrieval.jds:
            L.append(f"- [岗位] {jd.role_name} @ {jd.company}  相似度 {jd.score}  `source={jd.source}`")
    if r.retrieval.cases:
        for c in r.retrieval.cases:
            L.append(f"- [案例] {c.role_name} @ {c.company}  相似度 {c.score}  `source={c.source}`")
    if r.retrieval.empty:
        L.append("- （低于相似度阈值，无匹配结果 —— 宁缺毋滥，不硬凑）")
    elif not r.retrieval.cases:
        # 岗位匹配到了、但没有上岸者 bg 案例：如实标注，不编造，引导补案例库
        L.append("- ⚠ bg 知识库正在完善中，暂无上岸者背景画像：案例库未收录该类岗位")

    L.append(f"\n### ③ 证据化差距分析 | 匹配度 **{report.match_score}/100** → {report.verdict}")
    for i, g in enumerate(report.gaps, 1):
        tag = "需证据" if g.needs_proof else ("满足" if g.status == "satisfied" else "差距")
        L.append(f"{i}. [{tag}] **{g.requirement}**")
        L.append(f"   - {g.gap_description}")
        if g.evidence:
            L.append(f"   - 依据：{g.evidence}")
        if g.suggestion:
            L.append(f"   - 建议：{g.suggestion}")
    if report.strengths:
        L.append("亮点：")
        L += [f"   + {s}" for s in report.strengths]

    L.append(f"\n### ④ 复核结论")
    if rev.approved:
        L.append("- ✅ **复核通过**，结论可信，可放心参考。")
    else:
        L.append("- ⚠ **复核拦截**：以下问题需修正后再参考 —")
        for f in rev.findings:
            if f.severity == "error":
                L.append(f"   - ✗ [{f.item}] {f.issue}")
    for c in rev.corrections:
        L.append(f"   - 修正：{c}")

    if report.top_suggestions:
        L.append("\n### ⑤ 简历修改建议（按优先级）")
        L += [f"{i}. {s}" for i, s in enumerate(report.top_suggestions, 1)]

    return "\n".join(L)
