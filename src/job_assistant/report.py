"""PipelineResult → 可读报告文本（CLI 与 web 智能体工具共用）。"""
from __future__ import annotations

import re

from job_assistant.analyzer.rules import GateStatus
from job_assistant.pipeline import PipelineResult

_GATE_MARK = {GateStatus.PASS: "[通过]", GateStatus.FAIL: "[不满足]", GateStatus.UNKNOWN: "[待证据]"}
_SEP = "\n---\n"


def _case_bg_brief(content: str, max_len: int = 120) -> str:
    """从案例 content 里提取「背景自述」行作简要展示；没有则回退前 max_len 字符。"""
    m = re.search(r"背景自述[:：]\s*(.+)", content)
    if m:
        bg = m.group(1).strip()
        return bg[:max_len] + "…" if len(bg) > max_len else bg
    return content[:max_len] + "…" if len(content) > max_len else content


def format_report(r: PipelineResult) -> str:
    """把一次完整分析格式化成 markdown 报告字符串。"""
    reqs, report, rev = r.reqs, r.report, r.review_result
    L: list[str] = []

    L.append(f"## 求职助手分析报告")
    L.append(f"- **岗位**：{reqs.role_name} @ {reqs.company or '(未写明)'} ［{reqs.role_category}］")
    L.append(f"- **摘要**：{reqs.summary}")
    L.append(f"- **来源**：{reqs.source or '(未标注)'}")
    L.append(_SEP)

    L.append("### ① 硬门槛校验")
    for g in r.gates:
        L.append(f"- {_GATE_MARK[g.status]} **{g.requirement.description}** — {g.reason}")
    L.append(_SEP)

    L.append("### ② 匹配岗位 & 上岸背景画像")
    if r.retrieval.jds:
        L.append("**匹配到的岗位：**")
        for jd in r.retrieval.jds:
            L.append(f"- {jd.role_name} @ {jd.company} ｜ 相似度 {jd.score} ｜ `{jd.source}`")
        L.append("")
    if r.retrieval.cases:
        L.append("**可借鉴的上岸背景案例：**")
        for c in r.retrieval.cases:
            L.append(f"- {c.role_name} @ {c.company} ｜ 相似度 {c.score} ｜ `{c.source}`")
            if c.content:
                L.append(f"  - 背景：{_case_bg_brief(c.content)}")
    if r.retrieval.empty:
        L.append("- （低于相似度阈值，无匹配结果 —— 宁缺毋滥，不硬凑）")
    elif not r.retrieval.cases:
        # 岗位匹配到了、但没有上岸者 bg 案例：如实标注，不编造，引导补案例库
        L.append("- ⚠ bg 知识库正在完善中，暂无上岸者背景画像：案例库未收录该类岗位")
    L.append(_SEP)

    L.append(f"### ③ 证据化差距分析 ｜ 匹配度 **{report.match_score}/100** → **{report.verdict}**")
    for i, g in enumerate(report.gaps, 1):
        tag = "需证据" if g.needs_proof else ("满足" if g.status == "satisfied" else "差距")
        L.append(f"**{i}. [{tag}] {g.requirement}**")
        L.append(f"  - {g.gap_description}")
        if g.evidence:
            L.append(f"  - 依据：{g.evidence}")
        if g.suggestion:
            L.append(f"  - 建议：{g.suggestion}")
        L.append("")
    if report.strengths:
        L.append("**亮点：**")
        L += [f"  - {s}" for s in report.strengths]
    L.append(_SEP)

    L.append("### ④ 复核结论")
    if rev.approved:
        L.append("- ✅ **复核通过**，结论可信。")
    else:
        err_count = sum(1 for f in rev.findings if f.severity == "error")
        L.append(f"- ⚠ **复核拦截**：发现 {err_count} 处问题，报告仅供参考。")
    L.append(_SEP)

    if report.top_suggestions:
        L.append("### ⑤ 简历修改建议（按优先级）")
        for i, s in enumerate(report.top_suggestions, 1):
            L.append(f"**{i}.** {s}")
            L.append("")

    return "\n".join(L).strip()
