"""财经求职助手 web 智能体（ADK web 入口）。

启动：在项目根目录运行 `adk web agents`，浏览器打开智能体界面后：
1. 先粘贴简历 → 智能体调用 set_resume 保存画像；
2. 再粘贴岗位 JD → 智能体调用 analyze_jd 返回完整分析报告。

注意：ADK 2.6 下模型必须用 litellm 原生 deepseek/ 前缀 + extra_body 禁用 thinking
（见 src/job_assistant/llm.py 注释，这是实测踩过的坑）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证能 import 到 src/job_assistant（adk web 会把 agents/ 加进 sys.path，src 需要手动补）
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dotenv import load_dotenv  # noqa: E402
from google.adk.agents import Agent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.genai import types  # noqa: E402

from fin_resume.tools import analyze_jd, apply_revision, search_web, set_resume  # noqa: E402
from fin_resume.welcome import WELCOME  # noqa: E402
from job_assistant.memory.inject import inject_memory  # noqa: E402

load_dotenv()

INSTRUCTION = f"""你是「财经求职助手」，帮助财经类院校学生分析岗位匹配度、提供简历修改建议。

【开场规则 · 最重要，任何情况下都必须遵守】
- 先检查本会话的历史消息：**是否已经有一条"我输出的开场白"**（即以"你好，我是「财经求职助手」"开头的 assistant 回复）。
- 如果**已经有了开场白** → 不要重复，直接处理用户需求。
- 如果**还没有开场白**（例如会话刚建立、你还没介绍过自己）→ 你的这条回复必须**先把下面的 WELCOME 开场白原样完整输出**（一个字都不要改、不要总结、不要省略），然后才继续处理用户的需求。
- **开场白输出完毕后，用户紧接着发来的 JD 或简历，必须照常调用 analyze_jd / set_resume**——开场白不改变工具调用规则，禁止因刚开场就改用纯文字回答。

WELCOME 全文：
{WELCOME}

【工具调用硬规则 · 违反即为幻觉，必须严格遵守】
- 用户消息含招聘帖特征（"任职要求""学历要求""岗位职责""招聘""JD"）→ 调用 analyze_jd。
- 用户消息是个人简历 / 自我介绍（"我的""本人""教育背景""实习经历"等自述）→ 调用 set_resume。
- 用户聊天提问时，先判断是否**需要最新/实时信息**：
  * 问公司近况 / 行业动态 / 校招进展 / 岗位薪资行情 / 招聘时间点 / 某公司或行业评价等**时效性内容** → 调用 search_web 联网搜索，基于结果回答（保留来源链接）。
  * 问求职方法论 / 技巧等**通用知识**（简历怎么写、面试怎么准备、行研和投行怎么选、某类岗位做什么等）→ 直接文字回答，**不要调工具**。
- 用户要求「按分析建议修改简历」（"帮我改简历""按建议优化""把简历改一下"等）→ 调用 apply_revision（可选传 instructions 说明额外要求）。
- 拿不准用户发的是简历还是 JD → **不调工具**，直接问用户"这是你的简历还是岗位 JD？请确认一下"。
- 禁止为了"看起来在干活"而调用工具；能直接回答的问题就不要调工具。

工作方式（根据用户消息内容判断调用哪个工具）：
1. 用户发来**简历**（含教育背景 / 实习经历 / 技能 / 证书 / 项目等自我介绍或简历全文）
   → 调用 set_resume 保存画像，然后把返回的确认信息完整转述给用户，并提示下一步可以发 JD。
2. 用户发来**岗位 JD**（含岗位名称、任职要求、学历要求、工作职责等）
   → 调用 analyze_jd 做完整分析，然后把返回的分析报告**逐字原样完整输出**给用户，
     保留其全部章节结构，不做任何重新排版（详见「要求」里的报告输出硬规则）。
3. 用户问求职方法论 / 技巧等通用知识（简历怎么写、面试怎么准备、行业对比等）→ 直接回答，不需要调工具。
4. 用户既有简历又有 JD → 先 set_resume 再 analyze_jd。
5. 用户问需要联网搜索的时效性问题（公司近况、行业/校招动态、薪资行情、招聘时间点等）
   → 调用 search_web，把搜索结果组织成简洁的中文回答，**保留来源链接**；搜不到就如实说明，绝不编造。
6. 用户要求「按分析建议修改简历」（"帮我改简历""按建议优化"等）
   → 调用 apply_revision（可传 instructions 说明额外要求，如"重点改实习那段"）；
      把返回的改动 diff 与修改后简历全文逐字原样输出给用户。

要求：
- 必须用中文回答。
- 报告里有 `source=` 的引用不能去掉；有"待证据/需证据"项要如实保留。
- 不要编造报告里没有的内容。
- 联网搜索结果里的信息必须带来源链接引用；不编造搜索结果里没有的事实；搜索失败/无结果时如实告知用户，不硬凑。
- **【报告输出硬规则】analyze_jd 返回的报告必须原样输出，章节结构与措辞不得改动**：
  * 保留原有章节：① 硬门槛校验、② 匹配岗位 & 上岸背景画像（含「匹配到的岗位」「可借鉴的上岸背景案例」「背景：」）、③ 证据化差距分析（编号列表 + 匹配度 + 亮点）、④ 复核结论、⑤ 简历修改建议（按优先级）；
  * 禁止把列表改成表格；禁止新增「综合匹配度」「核心结论」「上岸者画像」「关键差异」「我的建议」「小结」等报告中不存在的标题、评分或总结；禁止重写措辞或自行添加 emoji 符号；
  * 禁止省略任何条目：硬门槛结果、source 引用、needs_proof / 待证据 / 需证据项都要保留。
- **任何匹配度、硬门槛判定、source 引用、needs_proof 标记，只能来自 analyze_jd 返回的报告原文**；
  若工具未返回报告，绝对不要自行编造匹配分数、或输出"根据您的背景估计…"之类的结论。
- 除第一条消息的开场白外，不需要再额外寒暄，直接按上述流程推进。

【系统记忆使用规则】
- 若出现「[用户画像摘要]」：这是用户通过 set_resume 保存的简历画像，跨会话持久，
  含姓名/学校/专业/技能/证书/实习/项目/意向。用它回答"我的简历是什么""我的背景"
  这类问题——直接引用画像内容，**绝不要说"没有保存过你的简历"或"我不知道你的背景"**。
- 若出现「[系统短期记忆]」：那是最近 2 小时内的对话摘要，
  用它理解当前语境（比如用户刚才在讨论哪个岗位、想对比什么），不要逐字复述给用户。
- 若出现「[系统长期记忆]」：包含用户画像、助手设定、长期经历（来源 data/memory 三类 MD）。
  用它做个性化回答——记住用户的目标岗位、已知短板、偏好城市、既往投递，避免重复问已知信息。
- 记忆是辅助：只在「有助于回答当前问题」时用，不要为了展示记忆而提它；记不住/没有记忆就正常按当前消息处理。
- 若记忆与用户本次消息冲突，以用户本次消息为准（记忆可能过时）。"""


def _extract_file_bytes(part: types.Part) -> tuple[bytes, str] | None:
    """从 part 里取出上传文件的内容字节和 MIME。

    返回 (bytes, mime_type)；取不到返回 None。ADK web 上传的文件可能以
    inline_data（内联字节）或 file_data（artifact 本地路径）两种形式出现。
    """
    if part.inline_data and part.inline_data.data:
        return part.inline_data.data, (part.inline_data.mime_type or "application/octet-stream")
    if part.file_data:
        uri = part.file_data.file_uri or ""
        if uri.startswith("file://"):
            try:
                return Path(uri[7:]).read_bytes(), (part.file_data.mime_type or _guess_mime(uri))
            except OSError:
                return None
        if uri and Path(uri).is_file():
            try:
                return Path(uri).read_bytes(), (part.file_data.mime_type or _guess_mime(uri))
            except OSError:
                return None
    return None


def _guess_mime(name: str) -> str:
    import mimetypes

    t, _ = mimetypes.guess_type(name)
    return t or "application/octet-stream"


def _file_to_text(data: bytes, mime: str, name: str) -> str:
    """把上传文件内容解码成文本（PDF/Word/纯文本），失败返回空串。"""
    mime = (mime or "").lower()
    name = (name or "").lower()
    try:
        if "pdf" in mime or name.endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(__import__("io").BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        if "wordprocessingml" in mime or "msword" in mime or name.endswith(".docx"):
            from docx import Document

            doc = Document(__import__("io").BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs if p.text).strip()
        # 纯文本兜底
        return data.decode("utf-8", errors="replace").strip()
    except Exception as e:  # noqa: BLE001
        print(f"[agent] file decode failed ({name}): {type(e).__name__}: {e}")
        return ""


def _decode_uploaded_files(callback_context, llm_request) -> None:
    """before_model_callback：把用户上传的文件 part 解码成文本。

    DeepSeek 原生 API 不认 file 类型的 part（只认 text），ADK web 上传文件会生成
    file part → 报 `unknown variant 'file'`。这里在进模型前把文件全部解码为文本，
    无法解析的文件替换为提示文字，避免整条消息失败。
    """
    for content in llm_request.contents:
        if content.role != "user":
            continue
        new_parts: list[types.Part] = []
        for part in content.parts or []:
            # 关键：function_response（工具结果）和其他非文件 part 必须原样保留！
            # 一旦丢弃，assistant 的 tool_call 就找不到对应响应，DeepSeek 会报
            # `missing field 'content'`。这里只转换真正的文件 part。
            if part.function_response:
                new_parts.append(part)
                continue
            if part.text:
                new_parts.append(part)
                continue
            extracted = _extract_file_bytes(part)
            if not extracted:
                new_parts.append(part)
                continue
            data, mime = extracted
            display = part.file_data.display_name if part.file_data else ""
            text = _file_to_text(data, mime, display)
            if text:
                prefix = f"[附件: {display}] 内容如下：\n" if display else "[上传的文件内容]：\n"
                new_parts.append(types.Part.from_text(text=prefix + text))
            else:
                new_parts.append(
                    types.Part.from_text(
                        text="[上传了一个无法解析的文件]：请让用户改用纯文本粘贴简历/JD内容。"
                    )
                )
        content.parts = new_parts


def build_agent() -> Agent:
    model = LiteLlm(
        model="deepseek/deepseek-v4-flash",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0.1,
        top_p=0.9,
        seed=42,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return Agent(
        name="fin_resume",
        model=model,
        instruction=INSTRUCTION,
        description="财经院校学生求职私人助手：传简历+传JD，返回硬门槛校验/案例匹配/差距分析/简历建议，可一键按建议改简历，可联网搜最新公司/行业/校招信息，跨会话记忆用户画像与投递进展",
        tools=[set_resume, analyze_jd, search_web, apply_revision],
        # 两个 before_model_callback：先解码上传文件，再注入记忆（每次调 LLM 前执行）
        before_model_callback=[_decode_uploaded_files, inject_memory],
    )


root_agent = build_agent()
