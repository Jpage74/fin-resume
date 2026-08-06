"""冒烟：resume_matcher 证据化差距分析（管线前两环打通后跑第三环）。

输入 JD → jd_analyzer → case_retriever → resume_matcher，输出完整 MatchReport。
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.analyzer.jd_analyzer import analyze_jd  # noqa: E402
from job_assistant.matcher.resume_matcher import match  # noqa: E402
from job_assistant.memory.profile import load_profile  # noqa: E402
from job_assistant.retriever.case_retriever import CaseRetriever  # noqa: E402
from job_assistant.retriever.seed import build_index  # noqa: E402

SAMPLE_JD = """公司：华泰证券研究所
岗位：行业研究实习生（消费方向）
【学历要求】重点院校硕士在读，2027 届优先；
【技能要求】熟练使用 Excel、Wind，掌握 Python 或 R 者加分；
【实习要求】有券商研究所实习经历者优先；"""


def main():
    print("=== 1) 解析 JD ===")
    reqs = analyze_jd(SAMPLE_JD, source="smoke:华泰行研实习")

    print("=== 2) RAG 检索 ===")
    retriever = CaseRetriever()
    build_index(retriever, verbose=False)
    result = retriever.retrieve(reqs)

    print("=== 3) 证据化差距分析 ===")
    report = match(reqs, load_profile(), result)
    print(json.dumps(json.loads(report.model_dump_json()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
