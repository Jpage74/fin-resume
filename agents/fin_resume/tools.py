"""web 智能体的工具：保存简历 / 分析 JD。

这些工具是 ADK Agent 的 function tools，LLM 根据用户消息决定调用哪个。
返回字符串会被智能体原样呈现给用户。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from job_assistant.pipeline import run_pipeline  # noqa: E402
from job_assistant.report import format_report  # noqa: E402
from job_assistant.resume.parser import profile_has_data, save_resume  # noqa: E402


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

    report = format_report(result)

    if not profile_has_data(result.profile):
        head = "⚠ **提示：你的画像还是空的**，下面的结果全部按「待证据」处理，仅供参考。先把简历发给我，分析会更准。\n\n"
        return head + report

    if not result.review_result.approved:
        report += "\n\n> ⚠ 复核未通过，输出仅供参考，请按修正建议核对。"
    return report
