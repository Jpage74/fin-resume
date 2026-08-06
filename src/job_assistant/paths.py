"""项目路径常量（集中定义，避免各模块各算一遍 parents）。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # C:\agent\求职助手
DATA_DIR = PROJECT_ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"  # 种子知识库（cases / jds 两类 yaml）
CHROMA_DIR = DATA_DIR / "chroma"        # 向量库持久化
