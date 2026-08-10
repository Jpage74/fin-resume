"""记忆注入：before_model_callback 里把 STM + LTM 拼进 system_instruction。

每次调模型前执行（ADK 的 before_model_callback 机制），从磁盘实时读
data/memory 下的记忆文件并追加到 LlmRequest 的 system_instruction。
因此无需重启服务，新的每日摘要 / 短期上下文会被下一次调用吃到。

注入内容：
1. STM 短期记忆（最近 20 分钟对话原文）
2. LTM 长期记忆（user_profile.md / agent_setting.md / dream.md 最近内容）
两者可独立缺失，谁有注入谁。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from job_assistant.memory.ltm import load_recent_md  # noqa: E402
from job_assistant.memory.stm import build_stm_context  # noqa: E402


def build_memory_context(
    stm_window_minutes: int = 20,
    ltm_limit_days: int = 3,
) -> str | None:
    """拼装注入 prompt 的记忆块。STM 和 LTM 都有才返回；都空返回 None。"""
    blocks = []
    stm = build_stm_context(window_minutes=stm_window_minutes)
    if stm:
        blocks.append(stm)
    ltm = load_recent_md(limit_days=ltm_limit_days)
    if ltm:
        blocks.append(ltm)
    if not blocks:
        return None
    return "\n\n".join(blocks)


def inject_memory(callback_context, llm_request) -> None:
    """before_model_callback 兼容签名：向 LlmRequest 追加记忆指令。"""
    try:
        ctx = build_memory_context()
        if ctx:
            llm_request.append_instructions([ctx])
    except Exception as e:  # noqa: BLE001
        # 记忆注入失败不影响主流程（记忆是辅助，不是必需）
        import traceback

        print(f"[memory] 注入失败: {type(e).__name__}: {e}")
        traceback.print_exc()
