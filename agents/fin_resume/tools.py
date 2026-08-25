"""web 智能体的工具：保存简历 / 分析 JD。

这些工具是 ADK Agent 的 function tools，LLM 根据用户消息决定调用哪个。
返回字符串会被智能体原样呈现给用户。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from job_assistant.analyzer.role_profiler import profile_role  # noqa: E402
from job_assistant.memory.history import add_feedback  # noqa: E402
from job_assistant.pipeline import run_pipeline, run_pipeline_reqs  # noqa: E402
from job_assistant.report import format_report  # noqa: E402
from job_assistant.resume.parser import profile_has_data, save_resume  # noqa: E402
from job_assistant.revision.apply_revision import apply_revision as _apply_revision  # noqa: E402
from job_assistant.revision.apply_revision import load_last_analysis, save_last_analysis  # noqa: E402
from job_assistant.search.web_search import web_search  # noqa: E402

# 报告尾部反馈提示（反馈回路入口，随报告一并返回）
_FEEDBACK_HINT = "\n\n---\n这份分析对你有帮助吗？回复「有用」或「不准 + 原因」，我会记录下来持续改进。"


def set_resume(resume_text: str) -> str:
    """保存/更新用户简历到画像。

    调用条件：仅在用户发送「个人简历或自我介绍」时调用（含教育背景/实习经历/技能/证书/项目等个人信息）。
    绝不能调用：用户发送的是岗位 JD（含"任职要求""学历要求""岗位职责""招聘"等招聘帖特征）→ 这是 analyze_jd 的职责。
    输入：简历全文（含教育背景、实习、技能、证书、项目等）。
    返回保存结果的确认信息与画像摘要。
    """
    try:
        profile = save_resume(resume_text)
    except Exception as e:
        return f"⚠ 简历解析失败：{type(e).__name__}: {e}。请确认简历文本完整后重试。"

    u = profile.get("user", {})
    skills = "、".join(s.get("name", "") for s in u.get("skills", []) if s.get("name"))
    certs = "、".join(u.get("certs", []))
    return (
        "✅ 简历已保存到画像！\n\n"
        f"- 姓名：{u.get('name') or '—'}  学校：{u.get('school') or '—'}  专业：{u.get('major') or '—'}  学历：{u.get('degree') or '—'}  绩点：{u.get('gpa') or '—'}\n"
        f"- 技能：{skills or '—'}\n"
        f"- 证书：{certs or '—'}\n"
        f"- 实习：{len(u.get('internships', []))} 段 | 项目：{len(u.get('projects', []))} 个\n\n"
        "接下来把一份岗位 JD 发给我，我会帮你做硬门槛校验、匹配案例和差距分析。"
    )


def analyze_jd(jd_text: str) -> str:
    """对一份岗位 JD 做完整求职分析（四环管线）。

    调用条件：仅在用户发送「岗位 JD」时调用（含岗位名称/任职要求/学历要求/工作职责/招聘等招聘帖特征）。
    绝不能调用：用户发送的是个人简历/自我介绍（"我的""本人""教育背景""实习经历"等自述）→ 这是 set_resume 的职责。
    不要调用：用户只是聊天提问（如"行研和投行怎么选"）→ 直接文字回答，不需要工具。
    输入：JD 全文（含岗位名称、任职要求、学历要求等）。
    返回：完整分析报告（硬门槛校验 / 匹配岗位&案例 / 差距分析 / 复核结论 / 修改建议）。
    """
    try:
        result = run_pipeline(jd_text, source="web:用户提交")
    except Exception as e:
        return f"⚠ 分析失败：{type(e).__name__}: {e}。可能是模型调用或知识库问题，请稍后重试。"

    # 落盘本次分析的结构化建议，供一键改简历（apply_revision）读取
    try:
        save_last_analysis(result)
    except Exception:
        pass

    report = format_report(result)

    if not profile_has_data(result.profile):
        head = "⚠ **提示：你的画像还是空的**，下面的结果全部按「待证据」处理，仅供参考。先把简历发给我，分析会更准。\n\n"
        return head + report + _FEEDBACK_HINT

    if not result.review_result.approved:
        report += "\n\n> ⚠ 复核未通过，输出仅供参考，请按修正建议核对。"
    return report + _FEEDBACK_HINT


def analyze_role(role_name: str) -> str:
    """只给岗位名（如"券商行研""银行管培生"）也能做完整分析（无需 JD 原文）。

    调用条件：用户只提到岗位/方向名称、没有给具体 JD 时（如"我想看行研岗的要求""四大审计要什么条件"）。
    不要调用：用户已粘贴完整 JD（含任职要求/岗位职责）→ 用 analyze_jd。
    输入：岗位名或方向（如"券商行研""银行管培""四大审计""PE股权投资""国企财务"）。
    返回：完整分析报告（硬门槛校验 / 匹配岗位&案例 / 差距分析 / 复核结论 / 修改建议）。
    """
    try:
        reqs = profile_role(role_name)
    except Exception as e:
        return (
            f"⚠ 岗位识别失败：{type(e).__name__}: {e}。"
            "请把岗位名写具体些（如「券商行研」「银行管培」「四大审计」），或直接粘贴完整 JD。"
        )

    try:
        result = run_pipeline_reqs(reqs)
    except Exception as e:
        return f"⚠ 分析失败：{type(e).__name__}: {e}。可能是模型调用或知识库问题，请稍后重试。"

    # 落盘本次分析的结构化建议，供一键改简历（apply_revision）读取
    try:
        save_last_analysis(result)
    except Exception:
        pass

    note = "🧭 未给具体 JD，已按岗位画像聚合典型要求（内置画像 + 知识库同类 JD + 联网搜索），仅供参考。\n\n"
    report = format_report(result)
    if not profile_has_data(result.profile):
        head = "⚠ **提示：你的画像还是空的**，下面的结果全部按「待证据」处理，仅供参考。先把简历发给我，分析会更准。\n\n"
        return note + head + report + _FEEDBACK_HINT
    if not result.review_result.approved:
        report += "\n\n> ⚠ 复核未通过，输出仅供参考，请按修正建议核对。"
    return note + report + _FEEDBACK_HINT


def record_feedback(rating: str, comment: str = "") -> str:
    """记录用户对最近一次分析报告的反馈（反馈回路）。

    调用条件：用户对刚才的分析表达评价时（"有用""有帮助""不准""这不对"等）。
    不要调用：本次会话还没做过任何分析（analyze_jd / analyze_role）时。
    rating：只能是「有用」或「不准」二选一，按用户意图传入。
    comment：可选，用户的补充说明原样传入（如不准的原因）。
    返回：记录确认信息。
    """
    rating = (rating or "").strip()
    if rating not in ("有用", "不准"):
        return "⚠ rating 只能是「有用」或「不准」。请先确认用户想表达的评价再调用。"

    analysis = load_last_analysis() or {}
    try:
        add_feedback(
            rating=rating,
            comment=(comment or "").strip(),
            role_category=analysis.get("role_category", ""),
            company=analysis.get("company") or "",
            role_name=analysis.get("role_name", ""),
            match_score=analysis.get("match_score"),
            verdict=analysis.get("verdict", ""),
        )
    except Exception as e:  # noqa: BLE001
        return f"⚠ 反馈保存失败：{type(e).__name__}: {e}。请稍后重试。"

    role = analysis.get("role_name") or "未知岗位"
    extra = f"\n- 补充说明：{comment.strip()}" if (comment or "").strip() else ""
    return (
        f"✅ 反馈已记录\n"
        f"- 评价：{rating}\n"
        f"- 关联分析：{role}{extra}\n"
        f"谢谢！这些反馈会用于持续改进分析质量。"
    )


def search_web(query: str) -> str:
    """联网搜索最新信息（Tavily）。

    调用条件：仅在用户问「需要最新/实时信息」的时效性问题时调用——公司近况、
    行业动态、校招进展、岗位薪资行情、某公司/行业评价、招聘季时间点等。
    不要调用：纯求职方法论/技巧（简历怎么写、面试怎么准备、行研和投行怎么选、
    某类岗位做什么等通用知识）→ 直接用内置知识回答，不必搜索。
    输入：搜索查询词（中文，简洁）。
    返回：带来源链接的搜索结果摘要，供组织回答。
    """
    return web_search(query)


def apply_revision(instructions: str = "") -> str:
    """一键修改简历：基于最近一次 JD 分析的修改建议改写简历并写回画像。

    调用条件：仅在用户明确要求「按分析建议修改 / 优化简历」时调用（如"帮我改简历""按建议优化""把简历改一下"）。
    不要调用：用户只是问简历怎么写、或还没分析过岗位 JD 时（工具会返回提示，照实转达即可）。
    instructions：可选，用户对修改的额外要求（如"重点改实习经历那段""整体简洁一点"）；无则空串，默认应用全部建议。
    返回：逐条改动 diff + 修改后简历全文，需原样转述给用户。
    """
    return _apply_revision(instructions)
