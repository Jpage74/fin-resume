"""web 智能体端到端冒烟测试：简历 → set_resume 工具；JD → analyze_jd 工具。

用 Runner + InMemorySessionService 模拟用户在智能体界面里分两条消息发简历和 JD，
验证 LLM 是否正确调度到两个 function tools，并拿到真实分析报告。

注意：ADK 2.6 下必须用 run_async + asyncio.run()（sync Runner.run 在 Windows 上会段错误）。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))

from dotenv import load_dotenv  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.adk.agents import Agent  # noqa: E402
from google.genai import types  # noqa: E402

from fin_resume.agent import root_agent  # noqa: E402

load_dotenv()

APP_NAME = "smoke_web_agent"


async def turn(session_service, runner: Runner, session_id: str, text: str) -> list:
    """发送一条用户消息，返回智能体回复片段（含 tool call / text）。"""
    content = types.Content(role="user", parts=[types.Part(text=text)])
    chunks = []
    async for event in runner.run_async(
        user_id=APP_NAME,
        session_id=session_id,
        new_message=content,
    ):
        if not event.is_final_response():
            continue
        for part in event.content.parts:
            if part.text:
                chunks.append(part.text)
            elif part.function_call:
                name = part.function_call.name
                args = {k: (str(v)[:120] + "…" if len(str(v)) > 120 else v) for k, v in (part.function_call.args or {}).items()}
                chunks.append(f"[tool_call] {name}({args})")
    return chunks


async def main() -> None:
    session_service = InMemorySessionService()
    session_id = (await session_service.create_session(
        app_name=APP_NAME,
        user_id=APP_NAME,
        state={},
    )).id
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

    resume = """张三，上海财经大学金融学硕士，GPA 3.6/4.0。
实习：华泰证券研究所行研实习生6个月，独立撰写行业深度报告；招商银行对公助理。
技能：Python（熟练）、Excel、Wind、SQL。
证书：证券从业资格、CET-6。
项目：新能源行业盈利预测模型，覆盖20家标的。"""

    print("=== 第 1 条：发简历 ===")
    for c in await turn(session_service, runner, session_id, resume):
        print(c)
    print()

    jd = """【卖方研究所 · 行业研究实习生】上海
职责：协助撰写行业深度报告、搭建盈利预测模型、整理数据库。
任职要求：金融/经济/会计等相关专业硕士在读；掌握 Excel、Wind；有行研/咨询实习经验者优先；每周3天以上，实习3个月以上。"""
    print("=== 第 2 条：发 JD ===")
    for c in await turn(session_service, runner, session_id, jd):
        print(c)
    print()


if __name__ == "__main__":
    asyncio.run(main())
    print("smoke_web_agent: PASS")
