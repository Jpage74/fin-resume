"""LiteLLM 统一模型网关。

所有 LLM 调用走这里，模型清单见 config/litellm.yaml。
开发期默认模型：deepseek-v4-flash（便宜够用）。
"""
import json
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


def complete_json(model: str = DEFAULT_MODEL, messages: list[dict] | None = None, **kwargs) -> dict:
    """调用模型并要求输出 JSON 对象，解析后返回 dict。

    DeepSeek 支持 OpenAI 兼容的 response_format={"type": "json_object"}。
    模型若拒收 response_format 则自动去掉重试；解析时兜底剥离 ```json 代码块
    与前后多余文字，截取首个 { 到末个 }。
    """
    if messages is None:
        messages = [{"role": "user", "content": "你好，回复一句话即可。"}]
    gen = {**DEFAULT_GEN, **kwargs}
    try:
        resp = litellm.completion(
            model=model,
            messages=messages,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
            **gen,
        )
    except Exception:
        # 兜底：部分模型/网关不支持 response_format，去掉再试一次
        resp = litellm.completion(
            model=model,
            messages=messages,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            extra_body={"thinking": {"type": "disabled"}},
            **gen,
        )
    return _parse_json(resp.choices[0].message.content)


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    # 剥掉 ```json ... ``` 代码块
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    # 截取首个 { 到末个 }，容忍模型在 JSON 前后加的说明文字
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"模型输出不是 JSON：{text[:200]}")
    return json.loads(text[start : end + 1])


if __name__ == "__main__":
    # 冒烟测试：直接验证 LiteLLM → DeepSeek 链路
    print(complete())
