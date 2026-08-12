"""记忆注入：before_model_callback 里把 STM + LTM + 用户画像 拼进 system_instruction。

每次调模型前执行（ADK 的 before_model_callback 机制），从磁盘实时读
记忆文件并追加到 LlmRequest 的 system_instruction。因此无需重启服务，
新的每日摘要 / 短期上下文会被下一次调用吃到。

注入内容：
1. 用户画像摘要（profile.yaml，跨会话持久——agent 认识用户的根基）
2. STM 短期记忆（最近 2 小时对话原文）
3. LTM 长期记忆（user_profile.md / agent_setting.md / dream.md 最近内容）
三者可独立缺失，谁有注入谁。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from job_assistant.memory.ltm import load_recent_md  # noqa: E402
from job_assistant.memory.profile import load_profile  # noqa: E402
from job_assistant.memory.stm import build_stm_context  # noqa: E402


def build_profile_summary() -> str | None:
    """从 profile.yaml 读用户画像，格式化为注入文本。无数据返回 None。"""
    try:
        profile = load_profile()
    except Exception:  # noqa: BLE001 画像读坏不影响主流程
        return None
    u = profile.get("user") or {}
    if not any(u.get(k) for k in ("name", "school", "major", "degree", "gpa")):
        return None
    lines = ["[用户画像摘要]（来自你通过 set_resume 保存的简历，跨会话持久）"]
    head = []
    for k, label in (("name", "姓名"), ("school", "学校"), ("major", "专业"),
                     ("degree", "学历"), ("gpa", "绩点")):
        if u.get(k):
            head.append(f"{label}：{u[k]}")
    if head:
        lines.append("- " + " | ".join(head))
    skills = "、".join(s.get("name", "") for s in u.get("skills", []) if s.get("name"))
    if skills:
        lines.append(f"- 技能：{skills}")
    certs = "、".join(u.get("certs") or [])
    if certs:
        lines.append(f"- 证书：{certs}")
    interns = u.get("internships") or []
    if interns:
        lines.append(f"- 实习：{len(interns)} 段，如「{interns[0]}」")
    projects = u.get("projects") or []
    if projects:
        names = "、".join(p.get("name", "") for p in projects if p.get("name"))
        lines.append(f"- 项目：{names}")
    if u.get("target_city"):
        lines.append(f"- 意向城市：{'、'.join(u['target_city'])}")
    if u.get("target_roles"):
        lines.append(f"- 意向岗位：{'、'.join(u['target_roles'])}")
    return "\n".join(lines)


def build_memory_context(
    stm_window_minutes: int = 120,
    max_messages: int = 20,
    ltm_limit_days: int = 3,
) -> str | None:
    """拼装注入 prompt 的记忆块。任一记忆块存在即返回；全空返回 None。"""
    blocks = []
    profile = build_profile_summary()
    if profile:
        blocks.append(profile)
    stm = build_stm_context(window_minutes=stm_window_minutes, max_messages=max_messages)
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
