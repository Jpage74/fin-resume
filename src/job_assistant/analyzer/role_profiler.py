"""岗位画像器（role_profiler）：只给岗位名 → 聚合典型要求 → JobRequirements。

设计文档「双输入源」第二路：不依赖 JD 原文，从「内置岗位画像 + 知识库同类 JD + 联网搜索」
三处聚合岗位典型要求，产出与 jd_analyzer 相同契约的 JobRequirements，走同一套后续管线
（硬门槛校验 → RAG 检索 → 差距分析 → reviewer 复核）。

防幻觉（核心）：
- 内置岗位画像 ROLE_PROFILES 是人工策展的「典型要求」保底，evidence_key 严格对齐受控词表，
  保证即使知识库 / 联网都拿不到内容，也能产出可被规则校验的、不越界的要求；
- 知识库同类 JD 与联网搜索是「真实来源」，LLM 只做聚合，不凭空新增；
- evidence_key 只能从受控词表选，source 记录来源构成（内置画像 + 知识库 N 条 + 联网），可溯源。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from job_assistant.llm import DEFAULT_MODEL, complete_json  # noqa: E402
from job_assistant.schemas import JobRequirements  # noqa: E402

load_dotenv()

# 与 schemas.py JobRequirements.role_category 描述对齐的 15 类岗位词表
ROLE_CATEGORIES = [
    "券商行研", "券商投行", "银行管培", "四大审计", "基金投研", "基金销售", "基金运营",
    "信托", "保险资管", "保险精算", "PE股权投资", "咨询顾问", "互联网财务", "国企财务", "考公事业单位",
]

# 岗位名关键词 → 类别（确定性优先，命中唯一才用，多命中/未命中交给 LLM 兜底）
ROLE_ALIASES = {
    "券商行研": ["行研", "行业研究", "研究助理", "研究所", "卖方研究", "股票研究", "投研助理"],
    "券商投行": ["投行", "ibd", "债券承做", "债承", "股权承做", "并购", "承销", "投行部"],
    "银行管培": ["银行", "管培", "总行", "分行", "客户经理", "柜员", "金融市场部"],
    "四大审计": ["审计", "四大", "会计", "事务所", "税务", "财务咨询", "普华", "德勤", "安永", "毕马威", "立信"],
    "基金投研": ["基金", "投研", "研究员", "投资研究", "公募", "基金经理", "研究岗"],
    "基金销售": ["基金销售", "渠道", "直销", "财富", "销售"],
    "基金运营": ["基金运营", "基金会计", "估值", "清算", "登记"],
    "信托": ["信托"],
    "保险资管": ["保险资管", "另类投资", "保险投资", "资产管理"],
    "保险精算": ["精算", "核保", "理赔", "保险"],
    "PE股权投资": ["pe", "vc", "股权投资", "私募", "投资分析", "一级市场", "战投"],
    "咨询顾问": ["咨询", "顾问", "战略", "esg咨询", "商业分析"],
    "互联网财务": ["财务bp", "商业分析", "数据分析", "财务分析", "互联网", "大厂", "商分"],
    "国企财务": ["国企", "央企", "财务部", "资金管理", "审计部", "财务岗"],
    "考公事业单位": ["考公", "公务员", "事业编", "税务局", "财政局", "人民银行", "金融监管", "银保监", "证监会", "选调"],
}

# 内置岗位画像（人工策展的典型要求保底）。evidence_key 必须严格取自受控词表
# （degree>= / cert: / skill: / internships>= / gpa>=），软性素质类填空串。
ROLE_PROFILES = {
    "券商行研": {
        "summary": "卖方/买方行业研究岗：撰写深度报告、盈利预测与估值、维护数据库。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士及以上学历（重点院校财经/理工复合背景优先）", "evidence_key": "degree>=硕士", "verdict_rule": "硕士及以上"},
            {"type": "hard", "category": "证书", "description": "具备证券从业资格者优先", "evidence_key": "cert:证券从业资格", "verdict_rule": "持有证券从业资格"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel、Wind 等数据工具", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "bonus", "category": "技能", "description": "掌握 Python/SQL 者加分", "evidence_key": "skill:python", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有券商研究所或行研相关实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "自驱力、抗压能力、文字功底与逻辑表达能力", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "券商投行": {
        "summary": "投行部/债券承做：IPO、并购重组、债券发行全流程，尽职调查与财务建模。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士及以上学历（本硕双一流/QS100 优先）", "evidence_key": "degree>=硕士", "verdict_rule": "硕士及以上"},
            {"type": "hard", "category": "证书", "description": "具备证券从业资格", "evidence_key": "cert:证券从业资格", "verdict_rule": "持有证券从业资格"},
            {"type": "bonus", "category": "证书", "description": "CPA/法考通过者加分", "evidence_key": "cert:cpa", "verdict_rule": None},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel/PPT，掌握财务建模", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "hard", "category": "实习", "description": "有投行/会计师事务所实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "抗压能力、责任心、细致，能适应高强度出差", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "银行管培": {
        "summary": "银行总行/分行管培生：轮岗培养，覆盖对公/零售/风控/金融市场等方向。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士学历（总行管培为主），本科可报分行/客户经理岗", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "bonus", "category": "证书", "description": "英语六级（CET-6）", "evidence_key": "cert:cet6", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有银行/金融相关实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "沟通表达、服务意识、团队协作", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "四大审计": {
        "summary": "四大/内资所审计、税务、财务咨询：年审、内控测试、底稿编制。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历（财经类专业优先）", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "bonus", "category": "证书", "description": "CPA 通过部分科目者优先", "evidence_key": "cert:cpa", "verdict_rule": None},
            {"type": "bonus", "category": "证书", "description": "英语六级（CET-6）", "evidence_key": "cert:cet6", "verdict_rule": None},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "hard", "category": "实习", "description": "有审计/事务所实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "抗压能力、细致严谨，能适应忙季加班", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "基金投研": {
        "summary": "基金/资管投资研究：行业研究、个股/债券研究、投资支持。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士及以上学历（理工/财经复合背景优先）", "evidence_key": "degree>=硕士", "verdict_rule": "硕士及以上"},
            {"type": "hard", "category": "证书", "description": "具备基金从业资格", "evidence_key": "cert:基金从业资格", "verdict_rule": "持有基金从业资格"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel、Wind/Choice 等数据终端", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "bonus", "category": "技能", "description": "掌握 Python 等编程者加分", "evidence_key": "skill:python", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有基金/券商/资管研究实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "研究热情、逻辑思维、抗压能力", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "基金销售": {
        "summary": "基金渠道/直销销售：客户开发与维护、产品路演。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "hard", "category": "证书", "description": "具备基金从业资格", "evidence_key": "cert:基金从业资格", "verdict_rule": "持有基金从业资格"},
            {"type": "hard", "category": "实习", "description": "有金融销售/渠道实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "沟通能力、亲和力、抗压能力", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "基金运营": {
        "summary": "基金运营/基金会计：估值核算、清算、登记、信息披露。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历（财会/金融专业优先）", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "hard", "category": "证书", "description": "具备基金从业资格", "evidence_key": "cert:基金从业资格", "verdict_rule": "持有基金从业资格"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel，细心核对数据", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "soft", "category": "软性素质", "description": "细致严谨、责任心强", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "信托": {
        "summary": "信托业务：固收/非标项目的尽调、交易结构与投后管理。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士及以上学历", "evidence_key": "degree>=硕士", "verdict_rule": "硕士及以上"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel，掌握财务分析", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "hard", "category": "实习", "description": "有信托/券商/资管实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "抗压能力、细致严谨", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "保险资管": {
        "summary": "保险资管：另类投资、固收、权益投资与投后管理。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士及以上学历", "evidence_key": "degree>=硕士", "verdict_rule": "硕士及以上"},
            {"type": "hard", "category": "证书", "description": "具备证券/基金从业资格者优先", "evidence_key": "cert:证券从业资格", "verdict_rule": "持有证券从业资格"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel，掌握估值建模", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "hard", "category": "实习", "description": "有资管/投资相关实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "抗压能力、逻辑思维", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "保险精算": {
        "summary": "精算岗：产品定价、准备金评估、核保理赔支持。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历（精算/数学/统计专业优先）", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel，掌握精算软件", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "bonus", "category": "证书", "description": "英语六级（CET-6）", "evidence_key": "cert:cet6", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有保险/精算相关实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "数学功底扎实、细致严谨", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "PE股权投资": {
        "summary": "PE/VC 投资分析：行业扫描、尽调、估值建模与投后管理。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "硕士及以上学历（理工/财经复合背景优先）", "evidence_key": "degree>=硕士", "verdict_rule": "硕士及以上"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel，掌握财务建模/估值", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "hard", "category": "证书", "description": "具备基金从业资格者优先", "evidence_key": "cert:基金从业资格", "verdict_rule": "持有基金从业资格"},
            {"type": "hard", "category": "实习", "description": "有 PE/VC/投行/咨询等实习经历者优先（多段优先）", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "商业敏感度、逻辑思维、抗压能力", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "咨询顾问": {
        "summary": "战略/管理咨询：行业研究、商业分析、方案交付。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历（重点院校优先）", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel/PPT", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "bonus", "category": "证书", "description": "英语六级（CET-6）及以上", "evidence_key": "cert:cet6", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有咨询/战略/商业分析实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "结构化思维、沟通表达、抗压能力", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "互联网财务": {
        "summary": "互联网财务/财务BP/商业分析：预算、经营分析、业务支持。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历（财会/金融专业优先）", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "bonus", "category": "技能", "description": "掌握 SQL 者加分", "evidence_key": "skill:sql", "verdict_rule": None},
            {"type": "bonus", "category": "证书", "description": "CPA 通过部分科目者优先", "evidence_key": "cert:cpa", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有财务/审计/商业分析实习经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "沟通协作、细心严谨", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "国企财务": {
        "summary": "国企/央企财务：财务核算、资金管理、预算与审计配合。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "bonus", "category": "证书", "description": "CPA 优先", "evidence_key": "cert:cpa", "verdict_rule": None},
            {"type": "hard", "category": "技能", "description": "熟练使用 Excel", "evidence_key": "skill:excel", "verdict_rule": "熟练 Excel"},
            {"type": "soft", "category": "软性素质", "description": "责任心、细致严谨、稳定性", "evidence_key": "", "verdict_rule": None},
        ],
    },
    "考公事业单位": {
        "summary": "财经类对口招录岗：税务、财政、人民银行、金融监管等。",
        "requirements": [
            {"type": "hard", "category": "学历", "description": "本科及以上学历（以招录公告为准，部分岗位要求硕士）", "evidence_key": "degree>=本科", "verdict_rule": "本科及以上"},
            {"type": "bonus", "category": "证书", "description": "英语六级（部分岗位要求）", "evidence_key": "cert:cet6", "verdict_rule": None},
            {"type": "hard", "category": "实习", "description": "有相关实习/学生工作经历者优先", "evidence_key": "internships>=1", "verdict_rule": "至少 1 段实习"},
            {"type": "soft", "category": "软性素质", "description": "政治素质、文字功底、沟通表达", "evidence_key": "", "verdict_rule": None},
        ],
    },
}

_CLASSIFY_PROMPT = """你是财经校招岗位分类器。把用户给的岗位名归到 15 类之一，只输出一个 JSON：{"role_category": "..."}。

15 类（只能选其一）：券商行研 / 券商投行 / 银行管培 / 四大审计 / 基金投研 / 基金销售 / 基金运营 / 信托 / 保险资管 / 保险精算 / PE股权投资 / 咨询顾问 / 互联网财务 / 国企财务 / 考公事业单位。

判断提示：行研/研究所/行业研究→券商行研；投行/债承/IBD/承做→券商投行；银行/管培/客户经理→银行管培；审计/四大/税务/会计师事务所→四大审计；基金投研/研究员→基金投研；基金销售/渠道→基金销售；基金运营/估值/清算→基金运营；信托→信托；保险资管/另类投资→保险资管；精算/核保/理赔→保险精算；PE/VC/股权投资/私募→PE股权投资；咨询/战略/ESG咨询→咨询顾问；财务BP/商分/互联网财务→互联网财务；国企/央企财务→国企财务；考公/公务员/事业编/税务局/人民银行→考公事业单位。

只输出 JSON，不要多余文字。"""

_ROLE_PROFILE_PROMPT = """你是资深财经行业招聘分析师。给定岗位大类（role_category）与岗位名，根据下面三份「真实依据」聚合出该类岗位的**典型任职要求**，输出与 JD 解析相同 schema 的 JSON。

三份依据（按可信度排序）：
1. 内置岗位画像：人工策展的典型要求，已给好 type / evidence_key / verdict_rule，作为要求主骨架。
2. 知识库同类 JD 原文：真实校招 JD，用于补充/校准要求措辞。
3. 联网搜索结果：真实公开信息（带 source），仅作补充参考。

只输出一个 JSON 对象，schema：
{
  "role_category": "岗位大类",
  "role_name": "岗位名",
  "company": null,
  "location": null,
  "summary": "该类岗位一句话中文摘要（30 字内）",
  "requirements": [
    {"type": "hard/soft/bonus", "category": "学历/证书/技能/经验/语言/其他/软性素质/时间出勤", "description": "要求描述", "evidence_key": "受控词表之一", "verdict_rule": "硬门槛判定规则自然语言；非硬门槛为 null"}
  ]
}

防幻觉规则（务必遵守）：
- 要求只能来自上述三份依据，**绝不凭空编造**典型要求。
- 以「内置岗位画像」为主骨架：其 type / evidence_key / verdict_rule 直接采用，description 可结合知识库 JD / 联网结果微调措辞，但不偏离原意，也不删减画像里已有的硬门槛。
- 知识库 JD 里反复出现、而画像里没有的明确要求（某证书/某技能/某年限），才补入，且 evidence_key 必须从受控词表选。
- 联网结果只用于「补充/确认」；若与画像、知识库冲突，以画像 + 知识库为准。联网结果本身不构成独立要求来源。
- evidence_key 受控词表（只能选其一）：degree>=博士 / degree>=硕士 / degree>=本科；cert:cpa / cert:cfa / cert:acca / cert:cet6 / cert:银行从业资格 / cert:证券从业资格 / cert:基金从业资格；skill:python / skill:sql / skill:excel / skill:vba / skill:stata / skill:spss；internships>=1 / internships>=3；gpa>=3.5 / gpa>=4.0。软性素质/时间出勤类 evidence_key 填空串 ""。
- hard=硬门槛；soft=软性素质/时间出勤；bonus=加分项。软性素质、时间出勤各归并为一条。
- 只输出 JSON，不要多余文字。"""


def classify_role(role_name: str, model: str = DEFAULT_MODEL) -> str:
    """岗位名 → 岗位大类（确定性别名优先，LLM 兜底）。"""
    name = (role_name or "").strip()
    if not name:
        raise ValueError("岗位名为空")

    hits = [cat for cat, kws in ROLE_ALIASES.items() if any(k.lower() in name.lower() for k in kws)]
    if len(hits) == 1:
        return hits[0]

    # 多命中 / 未命中 → LLM 分类（受控到 15 类）
    try:
        data = complete_json(
            model=model,
            messages=[
                {"role": "system", "content": _CLASSIFY_PROMPT},
                {"role": "user", "content": f"岗位名：{name}"},
            ],
        )
        cat = (data.get("role_category") or "").strip()
        if cat in ROLE_CATEGORIES:
            return cat
    except Exception:
        pass
    # LLM 失败时回退：多命中取第一个，否则抛错让上层给出友好提示
    if hits:
        return hits[0]
    raise ValueError(f"无法识别岗位类别：{name}")


def _gather_kb(category: str, limit: int = 4) -> list[str]:
    """知识库中该类的真实 JD 原文（截断，供聚合）。"""
    from job_assistant.retriever.seed import jd_document, load_yaml_docs  # noqa: E402

    docs = [d for d in load_yaml_docs("jds") if d.get("role_category") == category]
    texts = []
    for d in docs[:limit]:
        t = (jd_document(d) or "").strip()
        if len(t) > 700:
            t = t[:700] + "…"
        if t:
            texts.append(t)
    return texts


def _gather_web(category: str, role_name: str) -> str:
    """联网搜索该类岗位当前典型要求（失败/未配置返回空串，不阻塞）。"""
    from job_assistant.search.web_search import web_search  # noqa: E402

    try:
        raw = web_search(f"{category} {role_name} 校招 任职要求")
    except Exception:
        return ""
    if not raw or raw.startswith("⚠"):
        return ""
    return raw


def profile_role(
    role_name: str,
    model: str = DEFAULT_MODEL,
    *,
    use_web: bool = True,
) -> JobRequirements:
    """岗位名 → 聚合典型要求 → JobRequirements（与 jd_analyzer 同契约）。"""
    category = classify_role(role_name, model=model)
    baseline = ROLE_PROFILES.get(category) or ROLE_PROFILES["券商投行"]

    kb_texts = _gather_kb(category)
    web_text = _gather_web(category, role_name) if use_web else ""

    user_content = "\n".join(
        [
            f"===== 目标岗位 =====",
            f"role_category={category}；role_name={role_name}",
            "===== 1. 内置岗位画像 =====",
            json.dumps({"summary": baseline["summary"], "requirements": baseline["requirements"]}, ensure_ascii=False, indent=1),
            "===== 2. 知识库同类 JD（真实校招 JD） =====",
            "\n\n".join(kb_texts) or "(该类暂无知识库 JD)",
            "===== 3. 联网搜索结果 =====",
            web_text or "(无，或未配置 TAVILY_API_KEY)",
        ]
    )
    data = complete_json(
        model=model,
        messages=[
            {"role": "system", "content": _ROLE_PROFILE_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    # 强制对齐分类结果与岗位名，防止 LLM 改类别/编公司
    data["role_category"] = category
    data["role_name"] = (data.get("role_name") or "").strip() or role_name.strip()
    data["company"] = None
    data["location"] = None
    web_flag = "+联网" if web_text else ""
    data["source"] = f"role_profiler:{category}（内置画像+知识库{len(kb_texts)}条{web_flag}）"
    return JobRequirements.model_validate(data)


if __name__ == "__main__":
    import sys as _sys

    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    reqs = profile_role("券商行研")
    print(reqs.model_dump_json(indent=2, ensure_ascii=False))
