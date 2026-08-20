"""一键修改简历：基于最近一次 JD 分析的修改建议，改写简历并写回画像。

设计（与「两轮预览→确认」不同，这里一步到位）：
    读最近一次分析（top_suggestions + 逐条 gaps 建议 + strengths + 岗位信息）
    + 当前简历原文 → LLM 生成「修改后简历全文 + 逐条 diff」→
    备份旧简历与旧画像 → 重新解析新版简历、合并写回画像 + 简历文本。

安全：写回前把旧版备份到 data/resume_backups/（带时间戳），可手动回滚。
防幻觉：只基于已保存的建议与简历原文改写，不新增经历 / 证书 / 技能 / 项目。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from job_assistant.llm import DEFAULT_MODEL, complete_json  # noqa: E402
from job_assistant.memory.profile import PROFILE_PATH  # noqa: E402
from job_assistant.paths import LAST_ANALYSIS_PATH, RESUME_BACKUP_DIR, RESUME_LATEST_PATH  # noqa: E402
from job_assistant.resume.parser import save_resume  # noqa: E402

load_dotenv()

REVISION_PROMPT = """你是深耕财经求职领域的专业简历顾问。根据「原始简历」「修改建议清单」「逐条差距建议」「现有亮点」「目标岗位」，把建议落到简历里，产出修改后的简历全文，并给出逐条 diff。只输出一个 JSON：

{
  "revised_resume": "修改后的完整简历全文（在原始简历基础上，把每条建议融入对应字段/段落；未涉及的内容原样保留，不删不改）",
  "changes": [
    {"field": "改的字段/段落", "before": "原文片段（无则写『（新增）』）", "after": "修改后片段", "reason": "为什么这样改（一句话，点出对标的岗位要求或专业术语）"}
  ]
}

规则（防幻觉，务必遵守）：
- 只基于「修改建议清单」与「逐条差距建议」改写，绝不新增简历里没有的经历、证书、技能、项目、量化数字。
- 建议里若只是"去补充XX行业知识/提前准备"，不要凭空在简历里写"已有该经历"；可体现在措辞强化或新增"行业追踪/关注方向"这类主动性表述，且必须可验证、不夸大。
- 措辞专业、量化，体现财经行业术语（投行→IPO/尽调/财务建模/DCF；行研→深度报告/盈利预测/估值模型/Wind；PE→尽调/估值/LBO/退出机制等），但不要写"参考了XX案例"。
- 「现有亮点」是用户简历里已被认可的部分，改写时保留、不要改弱或删掉。
- 未涉及的建议或简历段落保持原样，不要为了显得改得多而乱改。
- 每条 change 必须能追溯到某条建议或某条差距；before 用简历原文片段，after 是改后片段。
- 只输出 JSON，不要多余文字。"""


def save_last_analysis(result, analysis_path: Path = LAST_ANALYSIS_PATH) -> None:
    """把一次四环分析的修改建议落盘，供 apply_revision 读取。"""
    report = result.report
    reqs = result.reqs
    payload = {
        "role_category": getattr(reqs, "role_category", ""),
        "role_name": getattr(reqs, "role_name", ""),
        "company": getattr(reqs, "company", None),
        "match_score": report.match_score,
        "verdict": report.verdict,
        "top_suggestions": list(report.top_suggestions),
        "strengths": list(report.strengths),
        "gaps": [
            {"requirement": g.requirement, "status": g.status, "suggestion": g.suggestion}
            for g in report.gaps
        ],
    }
    analysis_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_last_analysis(analysis_path: Path = LAST_ANALYSIS_PATH) -> dict | None:
    if not analysis_path.exists():
        return None
    try:
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_resume_text(resume_path: Path = RESUME_LATEST_PATH) -> str | None:
    if not resume_path.exists():
        return None
    text = resume_path.read_text(encoding="utf-8").strip()
    return text or None


def _backup_old(
    resume_path: Path = RESUME_LATEST_PATH,
    profile_path: Path = PROFILE_PATH,
    backup_dir: Path = RESUME_BACKUP_DIR,
) -> str | None:
    """备份旧简历与旧画像（带时间戳），返回备份目录；无旧版可备时返回 None。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backed = False
    if resume_path.exists():
        (backup_dir / f"resume_{stamp}.txt").write_text(
            resume_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        backed = True
    if profile_path.exists():
        (backup_dir / f"profile_{stamp}.yaml").write_text(
            profile_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        backed = True
    return str(backup_dir) if backed else None


def generate_revision(
    instructions: str = "",
    model: str = DEFAULT_MODEL,
    *,
    resume_path: Path = RESUME_LATEST_PATH,
    analysis_path: Path = LAST_ANALYSIS_PATH,
) -> dict:
    """生成「修改后简历全文 + 逐条 diff」，不写盘。

    无分析或无简历时返回 {"error": "no_analysis"} / {"error": "no_resume"}（不发 LLM 调用）。
    """
    analysis = load_last_analysis(analysis_path)
    if not analysis or not analysis.get("top_suggestions"):
        return {"error": "no_analysis"}
    resume = load_resume_text(resume_path)
    if not resume:
        return {"error": "no_resume"}

    suggestion_lines = "\n".join(
        f"{i}. {s}" for i, s in enumerate(analysis["top_suggestions"], 1)
    )
    gap_lines = "\n".join(
        f"- [{g.get('status', '')}] {g.get('requirement', '')}｜建议：{g.get('suggestion', '')}"
        for g in analysis.get("gaps", [])
    )
    strength_lines = "\n".join(f"- {s}" for s in analysis.get("strengths", []))
    role_info = (
        f"{analysis.get('role_category', '')} {analysis.get('role_name', '')}"
        f" @{analysis.get('company') or ''}"
    )

    user_content = "\n".join(
        [
            "===== 原始简历 =====",
            resume,
            "===== 修改建议（按优先级） =====",
            suggestion_lines,
            "===== 逐条差距建议 =====",
            gap_lines or "(无)",
            "===== 现有亮点（改简历时保留，不要改弱） =====",
            strength_lines or "(无)",
            "===== 目标岗位 =====",
            role_info,
            "===== 用户额外要求 =====",
            instructions.strip() or "(无，按全部建议改)",
        ]
    )
    data = complete_json(
        model=model,
        messages=[
            {"role": "system", "content": REVISION_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    return data


def apply_revision(
    instructions: str = "",
    model: str = DEFAULT_MODEL,
    *,
    resume_path: Path = RESUME_LATEST_PATH,
    analysis_path: Path = LAST_ANALYSIS_PATH,
    profile_path: Path = PROFILE_PATH,
    backup_dir: Path = RESUME_BACKUP_DIR,
) -> str:
    """一键修改简历：生成 → 备份 → 写回，返回给用户的 diff 摘要。"""
    if not load_last_analysis(analysis_path):
        return "⚠ 还没有可用的分析结果：请先发送一份岗位 JD 让我分析，再让我改简历。"
    if not load_resume_text(resume_path):
        return "⚠ 还没有保存过简历：请先把简历发给我，再让我改简历。"

    data = generate_revision(
        instructions=instructions, model=model,
        resume_path=resume_path, analysis_path=analysis_path,
    )
    revised = (data.get("revised_resume") or "").strip()
    changes = data.get("changes") or []
    if not revised:
        return "⚠ 生成修改失败：模型未返回修改后的简历，请重试。"

    backup_dir_str = _backup_old(
        resume_path=resume_path, profile_path=profile_path, backup_dir=backup_dir
    )

    # 写回：重新解析新版简历 → 合并画像 + 写回简历文本
    try:
        save_resume(revised, path=profile_path, resume_path=resume_path)
    except Exception as e:  # noqa: BLE001
        return f"⚠ 应用失败：{type(e).__name__}: {e}。旧版已备份，可手动恢复。"

    lines = [f"✅ 简历已按分析建议修改完成，共 {len(changes)} 处改动："]
    for i, c in enumerate(changes, 1):
        lines.append(
            f"**{i}. 【{c.get('field', '')}】**\n"
            f"  - 原文：{c.get('before', '')}\n"
            f"  - 改为：{c.get('after', '')}\n"
            f"  - 理由：{c.get('reason', '')}"
        )
    lines.append("")
    lines.append("——— 修改后简历全文 ———")
    lines.append(revised)
    if backup_dir_str:
        lines.append("")
        lines.append(f"（旧版已备份到 `{backup_dir_str}/`，如需回滚可手动恢复）")
    lines.append("")
    lines.append("想针对某一段继续微调，直接说（如“实习经历那段再改具体点”），我会基于最新简历再改。")
    return "\n".join(lines)


if __name__ == "__main__":
    print(apply_revision())
