# Fin-Resume · 求职助手 Agent

基于 **Google ADK** + **LiteLLM** 的多智能体求职辅助项目，服务**财经类院校学生**的校招求职场景。

> ⚠️ 当前仅含设计文档，代码骨架待开发。

## 目标
输入 JD + 简历 → 岗位要求解析 → 差异分析 & RAG 优秀案例检索 → 汇总报告 + 修改意见 → 用户确认一键修改。

## 技术栈
- Google ADK（多 agent 编排）
- LiteLLM（统一模型网关，默认 DeepSeek `deepseek-v4-flash`）
- 记忆层：用户画像 `profile.yaml` + 投递历史 SQLite（规划中）
- RAG：Chroma 向量库（规划中）

## Roadmap
- [ ] MVP：JD 解析 + 差异分析 + RAG 案例检索
- [ ] 记忆层：用户画像 + 投递历史
- [ ] 防幻觉：reviewer 复核 + RAG 评测（recall@k）
- [ ] 定时收集：GitHub Actions cron

## 隐私
用户画像含真实个人信息，默认 `.gitignore` 排除、本地存储，不上传。
