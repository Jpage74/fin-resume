"""LiteLLM 统一模型网关。

所有 LLM 调用走这里，模型清单见 config/litellm.yaml。
开发期默认模型：deepseek-v4-flash（便宜够用）。
"""
import os

import litellm
from dotenv import load_dotenv

load_dotenv()  # 读取 .env

# 统一生成参数：低温 + 低 top_p + 固定 seed，输出稳定可复现
DEFAULT_GEN = {"temperature": 0.1, "top_p": 0.9, "seed": 42}

# 默认模型（OpenAI 兼容前缀 + DeepSeek base）
DEFAULT_MODEL = "openai/deepseek-v4-flash"


def complete(model: str = DEFAULT_MODEL, messages: list[dict] | None = None, **kwargs) -> str:
    """经 LiteLLM 调用模型，返回文本内容。"""
    if messages is None:
        messages = [{"role": "user", "content": "你好，回复一句话即可。"}]
    gen = {**DEFAULT_GEN, **kwargs}
    # 禁用 thinking：deepseek 是推理模型，不开则多出 reasoning_content，与 ADK 配合易误读
    resp = litellm.completion(
        model=model,
        messages=messages,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        extra_body={"thinking": {"type": "disabled"}},
        **gen,
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    # 冒烟测试：直接验证 LiteLLM → DeepSeek 链路
    print(complete())
