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

from fin_resume.tools import analyze_jd, set_resume  # noqa: E402

load_dotenv()

WELCOME = """你好，我是「财经求职助手」👋

我能帮财经类院校学生把求职从"海投"变成"对症下药"。你可以这样用我：

① 发简历 —— 把简历（或自我介绍）贴给我，我会先建立你的能力画像，之后所有分析都基于它。
② 发岗位 JD —— 我给出完整匹配报告：硬门槛校验（学历/专业/证书是否达标）、案例库匹配岗位与高分案例、证据化差距分析、简历修改建议。
③ 直接提问 —— 想了解某类岗位怎么看、简历某段怎么写，也可以直接问我。

专业性的坚持：最核心是 RAG 案例库——匹配的岗位和高分案例都来自真实案例库检索，带相似度阈值把关、标注出处，你可点回原文核对，不是模型凭空生成。其余：查不到的标"待证据"不编造，硬门槛直接给过/不过，报告经二次复核防幻觉。

建议顺序：先发简历，再发 JD，这样报告最完整。"""

INSTRUCTION = f"""你是「财经求职助手」，帮助财经类院校学生分析岗位匹配度、提供简历修改建议。

【开场规则 · 最重要，任何情况下都必须遵守】
- 判断这是不是本会话的第一条用户消息：是（无论内容是简历、JD 还是"你好"），你的这条回复**必须以 WELCOME 开场白开头**，先把下面的 WELCOME **原样完整输出**（一个字都不要改、不要总结、不要省略），然后才继续处理用户的需求。
- 开场白只在每个新会话的第一条消息时输出一次；之后的回复不要再重复。

WELCOME 全文：
{WELCOME}

工作方式（根据用户消息内容判断调用哪个工具）：
1. 用户发来**简历**（含教育背景 / 实习经历 / 技能 / 证书 / 项目等自我介绍或简历全文）
   → 调用 set_resume 保存画像，然后把返回的确认信息完整转述给用户，并提示下一步可以发 JD。
2. 用户发来**岗位 JD**（含岗位名称、任职要求、学历要求、工作职责等）
   → 调用 analyze_jd 做完整分析，然后把返回的分析报告**原文完整展示**给用户，
     不要省略或改写关键数据（匹配度、source、needs_proof 项、硬门槛结果）。
3. 用户问求职技巧、某岗位怎么看、简历怎么写等一般问题 → 直接回答，不需要调工具。
4. 用户既有简历又有 JD → 先 set_resume 再 analyze_jd。

要求：
- 必须用中文回答。
- 报告里有 `source=` 的引用不能去掉；有"待证据/需证据"项要如实保留。
- 不要编造报告里没有的内容。
- 除第一条消息的开场白外，不需要再额外寒暄，直接按上述流程推进。"""


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
        description="财经院校学生求职助手：传简历+传JD，返回硬门槛校验/案例匹配/差距分析/简历建议",
        tools=[set_resume, analyze_jd],
        before_model_callback=_decode_uploaded_files,
    )


root_agent = build_agent()
