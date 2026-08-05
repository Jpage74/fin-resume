"""链路验证第一步：纯 LiteLLM → DeepSeek。

只验证「LiteLLM 配置 + API key + 模型名」三者是否通，先不引入 ADK，
出问题好定位。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.llm import complete  # noqa: E402

if __name__ == "__main__":
    print(">>> 调用 deepseek-v4-flash ...")
    print(complete())
    print(">>> LiteLLM → DeepSeek 链路 OK")
