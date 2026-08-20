"""项目路径常量（集中定义，避免各模块各算一遍 parents）。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # C:\agent\求职助手
DATA_DIR = PROJECT_ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"  # 种子知识库（cases / jds 两类 yaml）
CHROMA_DIR = DATA_DIR / "chroma"        # 向量库持久化
MEMORY_DIR = DATA_DIR / "memory"        # 记忆层：STM / LTM 三类 MD 文件
SESSION_DB = PROJECT_ROOT / "agents" / "fin_resume" / ".adk" / "session.db"  # ADK 会话存储

# 一键修改简历（apply_revision）相关：简历原文 / 最近分析建议 / 旧版备份
RESUME_LATEST_PATH = DATA_DIR / "resume_latest.txt"    # 最近一次保存的简历原文（一键改简历读写）
LAST_ANALYSIS_PATH = DATA_DIR / "last_analysis.json"   # 最近一次岗位分析的结构化建议（一键改简历读）
RESUME_BACKUP_DIR = DATA_DIR / "resume_backups"        # 一键改简历前的旧版备份（回滚用）
