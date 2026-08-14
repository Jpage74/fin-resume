"""联网搜索（Tavily）：给主 agent 提供实时信息检索能力。

用途：求职助手的内置知识有截止日期，用户问「公司近况 / 行业动态 / 校招进展 /
薪资行情 / 招聘时间点」等时效性问题时，走这里联网搜最新结果。

设计（与现有防幻觉约定一致，见设计文档六）：
- 结果必须带 source（url），可溯源；
- 搜不到就如实返回「无结果」，不硬凑、不编造；
- 封装成纯函数，未来可被 analyze_jd 管线复用（如搜公司背景）。
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MAX_RESULTS = 5
_CONTENT_LIMIT = 500  # 单条摘要截断长度，控制喂给 LLM 的 token 量


def _clip(text: str, limit: int = _CONTENT_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """用 Tavily 联网搜索，返回带来源链接的格式化结果文本。

    Args:
        query: 搜索查询词（中文）。
        max_results: 返回条数上限，默认 5。

    Returns:
        格式化后的结果文本，含标题 / 来源 url / 摘要；失败或空结果返回说明文字。
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "⚠ 未配置 TAVILY_API_KEY，无法联网搜索。请在 .env 里补上该环境变量后重试。"

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results)
    except Exception as e:  # noqa: BLE001
        return f"⚠ 联网搜索失败：{type(e).__name__}: {e}。请稍后重试。"

    results = resp.get("results") or []
    if not results:
        return f"【联网搜索】「{query}」未搜到相关结果。"

    lines = [f"【联网搜索】「{query}」返回 {len(results)} 条结果："]
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = _clip(r.get("content") or "")
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   来源：{url}")
        if content:
            lines.append(f"   摘要：{content}")
    return "\n".join(lines)
