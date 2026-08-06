"""JD 解析子 agent：原始 JD → 结构化 JobRequirements。

管线第一环。设计文档七.1：JD 与岗位名双输入，先做 JD 直解析。
输出是「标准化 JobRequirements」契约，case_retriever / resume_matcher 都吃它。

调用约定（全项目统一）：
- LiteLlm/LLM 一律带 extra_body={"thinking": {"type": "disabled"}}（DeepSeek 推理模型坑）
- 中文指令 + 低温 / 低 top_p / 固定 seed
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from job_assistant.llm import DEFAULT_MODEL, complete_json  # noqa: E402
from job_assistant.schemas import JobRequirements  # noqa: E402

load_dotenv()

EXTRACT_PROMPT = """你是一名资深的财经行业招聘分析师。解析下面给出的岗位 JD，抽取结构化的岗位需求，输出 JSON。

只输出一个 JSON 对象，schema：
{
  "role_category": "岗位归类，从这些取值：券商行研 / 券商投行 / 银行管培 / 四大审计 / 基金投研 / 保险精算 / 咨询顾问 / 互联网财务 / 国企财务 / 考公事业单位",
  "role_name": "岗位名称",
  "company": "公司名（没有则为 null）",
  "location": "工作城市（没有则为 null）",
  "summary": "JD 一句话中文摘要（30 字以内）",
  "requirements": [
    {
      "type": "hard 或 soft 或 bonus",
      "category": "学历 / 证书 / 技能 / 经验 / 语言 / 其他",
      "description": "该需求的中文描述",
      "evidence_key": "从下方受控词表里选能精确对应的一条",
      "verdict_rule": "硬门槛判定规则的自然语言，如『硕士及以上』『持有 CPA』；非硬门槛填 null"
    }
  ]
}

evidence_key 受控词表（规则校验阶段用它在用户画像里定位证据，只能从这里选）：
- 学历：degree>=硕士 / degree>=本科
- 证书：cert:cpa / cert:cfa / cert:acca / cert:cet6 / cert:银行从业资格 / cert:证券从业资格 / cert:基金从业资格
- 技能：skill:python / skill:sql / skill:excel / skill:vba / skill:stata / skill:spss
- 实习：internships>=1 / internships>=3
- 绩点：gpa>=3.5 / gpa>=4.0
若 JD 里的要求在词表里没有精确对应项，选最接近的一条；实在对不上选一张描述最贴切的，并把规则写清进 description。

规则：
- hard = 硬门槛（不满足不该投）；soft = 软性素质（可权衡）；bonus = 优先加分项。
- 只抽取 JD 里明确写出的要求，不臆造、不补常识性内容。
- 只输出 JSON，不要任何多余文字。"""


def analyze_jd(jd_text: str, source: str = "", model: str = DEFAULT_MODEL) -> JobRequirements:
    """输入原始 JD 文本，返回标准化 JobRequirements。

    Args:
        jd_text: 岗位 JD 原文。
        source: JD 来源标识（渠道+编号），用于溯源；空则留空。
        model: 模型名，默认走网关默认模型。

    Raises:
        ValidationError: LLM 输出无法通过 schema 校验（可重试）。
    """
    messages = [
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content": f"=== 岗位 JD ===\n{jd_text}\n=== 结束 ==="},
    ]
    data = complete_json(model=model, messages=messages)
    if source:
        data["source"] = source
    return JobRequirements.model_validate(data)


if __name__ == "__main__":
    # 冒烟：解析一段样例券商行研 JD
    sample = """公司：华泰证券研究所
岗位：行业研究实习生（消费方向）
【学历要求】重点院校硕士在读，2027 届优先；
【证书要求】有证券从业资格证者优先；
【技能要求】熟练使用 Excel、Wind，掌握 Python 或 R 者加分；
【实习要求】有券商研究所实习经历者优先；
【其他】每周实习 4 天以上，至少实习 3 个月，有较强的抗压能力与文字功底。"""
    reqs = analyze_jd(sample, source="smoke:华泰行研实习")
    print(reqs.model_dump_json(indent=2, ensure_ascii=False))
