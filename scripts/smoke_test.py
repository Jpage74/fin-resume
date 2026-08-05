"""链路验证第二步：ADK Agent → LiteLLM → DeepSeek。

验证 ADK 主 agent 能通过 LiteLlm 调 deepseek-v4-flash 完成一轮对话。
适配 ADK 2.6：LiteLlm 位于 google.adk.models.lite_llm；
Content 来自 google.genai.types；session 用同步 create_session_sync。
"""
import os
import sys
from pathlib import Path

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


def main():
    model = LiteLlm(
        model="openai/deepseek-v4-flash",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        temperature=0.1,
        top_p=0.9,
    )
    agent = Agent(
        name="job_assistant",
        model=model,
        instruction="你是一个财经求职助手。保持回答简洁。",
    )

    session_service = InMemorySessionService()
    session_service.create_session_sync(
        app_name=APP_NAME, user_id="test_user", session_id=SESSION_ID
    )

    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    events = runner.run(
        user_id="test_user",
        session_id=SESSION_ID,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="你好，用一句话介绍你能帮财经院校学生做什么。")],
        ),
    )

    for event in events:
        if event.is_final_response():
            text = event.content.parts[0].text if event.content and event.content.parts else "(空)"
            print(">>> ADK Agent 回复：")
            print(text)
    print(">>> ADK → LiteLLM → DeepSeek 链路 OK")


if __name__ == "__main__":
    main()
