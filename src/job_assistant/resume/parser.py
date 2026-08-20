"""简历解析：自由文本简历 → 结构化画像（profile.yaml 的 user 结构）。

web 智能体/CLI 都从这里把简历落进画像，之后 analyze_jd 用它做差距分析。
防幻觉：简历里没有的信息留空，不编造。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from job_assistant.llm import DEFAULT_MODEL, complete_json  # noqa: E402
from job_assistant.memory.profile import load_profile, save_profile  # noqa: E402
from job_assistant.paths import RESUME_LATEST_PATH  # noqa: E402

load_dotenv()

RESUME_PROMPT = """你是一名简历信息抽取器。从候选人简历文本中提取结构化信息，输出 JSON。

JSON schema（对应 profile.yaml 的 user 字段）：
{
  "name": "姓名",
  "school": "学校",
  "major": "专业",
  "degree": "本科/硕士/博士等",
  "gpa": "绩点，如 3.5/4.0；无则空串",
  "target_roles": ["意向岗位"],
  "target_city": ["意向城市"],
  "constraints": ["限制条件，如每周可实习天数"],
  "skills": [{"name": "Python", "level": "中/高/熟练等", "evidence": "证明来源：课程/项目/证书"}],
  "certs": ["CPA", "CET-6", "证券从业资格"],
  "internships": ["公司-岗位（时长，可加成果要点）"],
  "projects": [{"name": "项目名", "detail": "内容与量化结果"}]
}

规则：
- 简历里没有的信息留空字符串或空列表，绝不编造。
- skills 的 evidence 写清"从哪能证明"（课程/项目/证书），没有就空串。
- internships / projects 尽量保留可量化的成果。
- 只输出 JSON，不要多余文字。"""


def parse_resume(resume_text: str, model: str = DEFAULT_MODEL) -> dict:
    """解析简历文本，返回 profile.yaml 的 user 结构（dict）。"""
    data = complete_json(
        model=model,
        messages=[
            {"role": "system", "content": RESUME_PROMPT},
            {"role": "user", "content": f"=== 简历 ===\n{resume_text}\n=== 结束 ==="},
        ],
    )
    return data


def save_resume(resume_text: str, path: Path | None = None, resume_path: Path | None = None) -> dict:
    """解析简历并合并保存到 profile.yaml，返回更新后的完整画像。

    合并策略（MVP 极简）：user 里新字段非空则覆盖，空则不覆盖已有内容。
    resume_path：简历原文落盘路径（一键改简历读取/写回用），默认 data/resume_latest.txt。
    """
    user = parse_resume(resume_text)
    profile = load_profile(path) if path else load_profile()
    profile["user"].update({k: v for k, v in user.items() if v not in (None, "", [])})
    save_profile(profile, path) if path else save_profile(profile)
    # 持久化简历原文（本地 gitignore，一键改简历读取/写回用）
    try:
        (resume_path or RESUME_LATEST_PATH).write_text(resume_text.strip(), encoding="utf-8")
    except Exception:
        pass
    return profile


def profile_has_data(profile: dict | None = None) -> bool:
    """画像是否已有实质内容（决定是否需要先提醒用户传简历）。"""
    if profile is None:
        profile = load_profile()
    u = profile.get("user", {})
    return any(
        u.get(f)
        for f in ("school", "major", "degree", "gpa", "name")
    ) or bool(u.get("skills") or u.get("certs") or u.get("internships"))


if __name__ == "__main__":
    sample = """张三，上海财经大学金融学硕士，GPA 3.6/4.0。
实习：华泰证券研究所行研实习生6个月，独立撰写行业深度报告；招商银行对公助理。
技能：Python（熟练）、Excel、Wind、SQL。
证书：证券从业资格、CET-6。
项目：新能源行业盈利预测模型，覆盖20家标的。"""
    p = save_resume(sample)
    import yaml

    print(yaml.safe_dump(p, allow_unicode=True, sort_keys=False))
