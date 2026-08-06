"""链路验证第二步：ADK Agent → LiteLLM → DeepSeek。

验证 ADK 主 agent 能通过 LiteLlm 调 deepseek-v4-flash 完成一轮对话。
适配 ADK 2.6：
- LiteLlm 位于 google.adk.models.lite_llm；Content 来自 google.genai.types；
- session 用同步 create_session_sync；
- ⚠️ 必须用 run_async：同步 Runner.run 是「另起线程 + queue 桥接」，在 Windows 上
  进程退出时段错误（exit 139），且会把 litellm 的 contextvars 搞乱。
- ⚠️ 模型用 litellm 原生 deepseek/ 前缀：openai/ + 自定义 api_base 在 async 路径
  会丢 api_key（Missing credentials），deepseek/ 读 DEEPSEEK_API_KEY env 稳定。
"""
import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402
from google.adk.agents import Agent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

load_dotenv()

APP_NAME = "job_assistant_app"
SESSION_ID = "smoke_session_1"


def build_agent():
    # deepseek-v4-flash 是推理模型，默认输出 reasoning_content，
    # ADK 2.6 会误把思考内容当回复。必须禁用它：extra_body={"thinking": {"type": "disabled"}}
    model = LiteLlm(
        model="deepseek/deepseek-v4-flash",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0.1,
        top_p=0.9,
        seed=42,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return Agent(
        name="job_assistant",
        model=model,
        instruction="你是一个财经求职助手。必须用中文回答。直接回答问题本身，不要复述指令，不要输出思考过程。",
    )


async def main():
    agent = build_agent()
    session_service = InMemorySessionService()
    session_service.create_session_sync(
        app_name=APP_NAME, user_id="test_user", session_id=SESSION_ID
    )
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    reply = None
    async for event in runner.run_async(
        user_id="test_user",
        session_id=SESSION_ID,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="你好，用一句话介绍你能帮财经院校学生做什么。")],
        ),
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                reply = "".join(p.text or "" for p in event.content.parts)
            else:
                reply = f"(无内容，错误: {event.error_message})"
    print(">>> ADK Agent 回复：")
    print(reply)
    print(">>> ADK → LiteLLM → DeepSeek 链路 OK")


if __name__ == "__main__":
    asyncio.run(main())
