"""启动 ADK web 智能体，并让 agent 在每次新会话创建时「主动」输出开场白。

标准 `adk web` 只会显示写死的 "Welcome to ADK!"，agent 不会主动开口。
本脚本 monkeypatch DevServer._create_session：会话创建成功后，立即往会话里
注入一条 assistant 开场白事件（WELCOME），这样用户打开新会话的第一眼就能
看到 agent 的自我介绍，而不是等用户先发消息。

用法：python run_web.py [port]   （默认 8000）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agents"))

from dotenv import load_dotenv  # noqa: E402
from google.adk.cli.dev_server import DevServer  # noqa: E402
from google.adk.events import Event  # noqa: E402
from google.genai import types  # noqa: E402

from fin_resume.welcome import WELCOME  # noqa: E402

load_dotenv()

_ORIG_CREATE_SESSION = DevServer._create_session


async def _create_session_with_welcome(self, *, app_name, user_id, session_id=None, state=None):
    session = await _ORIG_CREATE_SESSION(
        self,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=state,
    )
    try:
        welcome_event = Event(
            author=app_name,
            content=types.Content(
                role="model",
                parts=[types.Part(text=WELCOME)],
            ),
            invocation_id="welcome-greeting",
        )
        await self.session_service.append_event(session=session, event=welcome_event)
        print(f"[run_web] 已向新会话注入开场白: {session.id}")
    except Exception as e:  # noqa: BLE001
        # 注入失败不阻塞会话创建（比如 CLI 工具触发的会话）
        print(f"[run_web] 开场白注入跳过: {type(e).__name__}: {e}")
    return session


# 只对 web dev server 的会话创建生效，不污染其他入口
DevServer._create_session = _create_session_with_welcome


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    from google.adk.cli.fast_api import get_fast_api_app
    import uvicorn

    app = get_fast_api_app(
        agents_dir=str(ROOT / "agents"),
        web=True,
        host="127.0.0.1",
        port=port,
        reload_agents=False,
    )
    print(f"Starting ADK web UI at http://127.0.0.1:{port}/dev-ui/")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, reload=False)
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
