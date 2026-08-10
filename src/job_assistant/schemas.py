"""跨环节共享的 Pydantic 结构化契约。

管线各环都围绕「标准化 JobRequirements」协作（设计文档七.1）：
    jd_analyzer（JD / 岗位名双输入）→ JobRequirements
    case_retriever 用它做检索，resume_matcher 用它做差距分析。
集中放这里，避免各子模块各定义一份漂移。
"""
from enum import Enum

from pydantic import BaseModel, Field


class RequirementType(str, Enum):
    """需求性质。"""

    HARD = "hard"    # 硬门槛：不满足不该投
    SOFT = "soft"    # 软性素质：可权衡
    BONUS = "bonus"  # 优先加分项


class Requirement(BaseModel):
    type: RequirementType = Field(description="hard / soft / bonus")
    category: str = Field(description="需求类别：学历 / 证书 / 技能 / 经验 / 语言 / 其他")
    description: str = Field(description="该需求的中文描述")
    evidence_key: str = Field(
        description="判定证据键名，规则校验阶段用它到用户画像里定位证据。"
        "受控词表见 EVIDENCE_KEYS，格式：degree>=硕士 / cert:cpa / skill:python / internships>=1 / gpa>=3.5"
    )
    verdict_rule: str | None = Field(default=None, description="硬门槛判定规则的自然语言，如『硕士及以上』；非硬门槛为 null")


class JobRequirements(BaseModel):
    """JD 解析后的标准化岗位需求（管线流转契约）。"""

    role_category: str = Field(description="岗位归类：券商行研 / 券商投行 / 银行管培 / 四大审计 / 基金投研 / 基金销售 / 基金运营 / 信托 / 保险资管 / 保险精算 / PE股权投资 / 咨询顾问 / 互联网财务 / 国企财务 / 考公事业单位")
    role_name: str = Field(description="岗位名称")
    company: str | None = None
    location: str | None = None
    summary: str = Field(description="JD 一句话中文摘要（30 字内）")
    requirements: list[Requirement] = Field(default_factory=list)
    source: str = Field(default="", description="JD 来源标识，如渠道+编号，便于溯源")

    @property
    def hard_requirements(self) -> list[Requirement]:
        return [r for r in self.requirements if r.type == RequirementType.HARD]

    @property
    def soft_requirements(self) -> list[Requirement]:
        return [r for r in self.requirements if r.type == RequirementType.SOFT]

    @property
    def bonus_requirements(self) -> list[Requirement]:
        return [r for r in self.requirements if r.type == RequirementType.BONUS]


# evidence_key 受控词表（与 profile.yaml 的 user 字段对应）
EVIDENCE_KEYS = [
    "degree>=博士", "degree>=硕士", "degree>=本科",
    "cert:cpa", "cert:cfa", "cert:acca", "cert:cet6",
    "cert:银行从业资格", "cert:证券从业资格", "cert:基金从业资格",
    "skill:python", "skill:sql", "skill:excel", "skill:vba", "skill:stata", "skill:spss",
    "internships>=1", "internships>=3",
    "gpa>=3.5", "gpa>=4.0",
]
