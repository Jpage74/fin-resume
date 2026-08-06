"""冒烟：RAG 检索链路（建索引 → 向量化 → 检索匹配岗位+案例）。

验证 case_retriever 端到端：种子库 yaml → Chroma → 输入 JobRequirements → 带 source 的结果。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.analyzer.jd_analyzer import analyze_jd  # noqa: E402
from job_assistant.retriever.case_retriever import CaseRetriever  # noqa: E402
from job_assistant.retriever.seed import build_index  # noqa: E402

SAMPLE_JD = """公司：华泰证券研究所
岗位：行业研究实习生（消费方向）
【学历要求】重点院校硕士在读，2027 届优先；
【技能要求】熟练使用 Excel、Wind，掌握 Python 或 R 者加分；
【实习要求】有券商研究所实习经历者优先；
【其他】每周实习 4 天以上，至少实习 3 个月，有较强的抗压能力。"""


def main():
    print("=== 1) 建索引 ===")
    retriever = CaseRetriever()
    stats = build_index(retriever)
    print("  向量库:", retriever.count())

    print("\n=== 2) 解析 JD ===")
    reqs = analyze_jd(SAMPLE_JD, source="smoke:华泰行研实习")

    print("\n=== 3) 检索 ===")
    result = retriever.retrieve(reqs, k=3)
    print(f"  匹配岗位 {len(result.jds)} 条 | 高分案例 {len(result.cases)} 条")
    for jd in result.jds:
        print(f"    [岗位] {jd.role_name} @{jd.company} 相似度{jd.score} source={jd.source}")
    for case in result.cases:
        print(f"    [案例] {case.role_name} @{case.company} 相似度{case.score} source={case.source}")
    if result.empty:
        print("  ⚠ 全部低于相似度阈值 —— 返回空（防幻觉，宁缺毋滥）")


if __name__ == "__main__":
    main()
