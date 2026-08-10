# Fin-Resume · 求职助手 Agent

基于 **Google ADK 2.6** + **LiteLLM** 的多智能体求职辅助项目，服务**财经类院校学生**的校招求职场景。

## 功能

输入 JD + 简历 → 四环处理管线 → 输出结构化匹配报告：

1. **JD 解析** → 硬门槛校验（学历 / 专业 / 证书 / 实习要求）
2. **RAG 案例库检索** → 匹配岗位 + 上岸者背景画像（相似度阈值把关，标注出处 `source=`）
3. **证据化差距分析** → 每项判断绑定简历证据；证据不足标「待证据」，不编造
4. **reviewer 复核** → 二次校验，拦截幻觉

报告含：硬门槛通过/不通过、匹配岗位与上岸者画像、亮点与差距、简历修改建议。

> 案例库素材形态为「背景画像」：来自公开校招分享（牛客 / 小红书等）中求职者
> 自愿公开的背景自述与面经（学校 + 专业 + 实习 + 证书 + 结果），已脱敏、标注出处。
> 不是完整简历——完整简历涉及个人信息，公开渠道不采集。

## 快速开始

```bash
# 1. 安装依赖（Windows）
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. 配置密钥（.env）
DEEPSEEK_API_KEY=sk-xxx

# 3. 启动 web 智能体（推荐）
python run_web.py          # 打开 http://127.0.0.1:8000/dev-ui/
# 或
run_web.bat

# 4. CLI 方式
python run_cli.py 简历.txt JD.txt
```

web 智能体 `fin_resume` 在每次**新建会话**时主动输出开场白（介绍功能与专业机制），
无需先发消息。支持直接上传 PDF / Word / 文本简历。

## 技术栈

- **Google ADK 2.6**（Agent + LiteLlm + Runner）
- **LiteLLM**（统一模型网关，默认 DeepSeek `deepseek-v4-flash`，关闭 thinking）
- **RAG**：Chroma 向量库 + fastembed（BAAI/bge-small-zh-v1.5）
- **文件解析**：pypdf（PDF）、python-docx（Word）
- **记忆**：用户画像 `data/profile.yaml` + 投递历史 SQLite + 短期记忆（STM 最近 20 分钟对话）+ 长期记忆（LTM 每日摘要 → `data/memory/` 三 MD）

## 目录结构

```
src/job_assistant/      # 四环管线：jd_analyzer / case_retriever / resume_matcher / reviewer
src/job_assistant/memory/  # 记忆层：profile / history / stm(短期) / ltm(长期摘要) / inject(注入)
agents/fin_resume/      # ADK web 智能体（agent.py 主逻辑 + tools.py 工具 + welcome.py 开场白）
scripts/                # 冒烟测试 / 评测脚本 / run_memory_digest.py（每日摘要）
run_web.py              # web 启动入口（含开场白注入）
run_web.bat / run_cli.bat
data/                   # 画像 / 向量库 / 知识库 / 记忆（本地存储，gitignore 排除）
```

## Roadmap

- [x] MVP：JD 解析 + 差异分析 + RAG 案例检索
- [x] web 可视化：ADK dev-ui 交互式智能体 + 文件上传 + 开场白
- [x] 防幻觉：证据绑定 + needs_proof + reviewer 复核 + RAG 评测（recall@k）
- [x] 种子数据：背景画像案例库（真实 bg 帖整理，当前券商行研/券商投行 3 案例 + 1 JD，持续扩充中）
- [x] 记忆层：用户画像 + 投递历史 + STM 短期记忆（20 分钟对话）+ LTM 长期记忆（每日摘要三 MD，`scripts/run_memory_digest.py`）
- [ ] 定时收集：GitHub Actions cron

## 隐私

用户画像、对话摘要含真实个人信息，默认 `.gitignore` 排除（`.env`、`data/profile.yaml`、`data/knowledge/`、`data/memory/`、`data/chroma/`）、本地存储，不上传。短期记忆从本地 `session.db`（ADK 会话日志）读取，同样不上传。
