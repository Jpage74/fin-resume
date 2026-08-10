"""记忆层：用户画像 + 投递历史 + 短期记忆(STM) + 长期记忆(LTM)。

四层记忆，职责不同：
- profile.yaml     机器可读画像，管线硬门槛校验消费（结构化）
- history.db       SQLite 投递历史，去重 / 跟踪（机器查询）
- STM 短期记忆     data/memory/stm_ctx.json，最近消息原文（无 LLM 压缩）
- LTM 长期记忆     data/memory/{user_profile,agent_setting,dream}.md，每日摘要
"""
