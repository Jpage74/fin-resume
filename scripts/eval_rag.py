"""RAG 评测：recall@k。

设计文档「防幻觉是持续工程，必须配 RAG 评测一起落地，否则难以证明有效」。
这里实现最朴素的指标：对种子库每条案例，用其 role_category + role_name + keywords
构造查询，看 top-k 内是否召回自身。

用法：
    python scripts/eval_rag.py            # 全量跑 recall@1 / recall@3
    python scripts/eval_rag.py 5          # 自定义 k
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.retriever.case_retriever import CaseRetriever  # noqa: E402
from job_assistant.retriever.seed import load_yaml_docs  # noqa: E402

DEFAULT_K = 3


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_K
    retriever = CaseRetriever()
    cases = load_yaml_docs("cases")
    if not cases:
        print("种子库为空，先补充 data/knowledge/cases/ 下的案例再评测")
        return
    # 重建索引，确保与评测对象一致
    from job_assistant.retriever.seed import build_index

    build_index(retriever, verbose=False)

    hit = 0
    for c in cases:
        q = f"{c.get('role_category','')} {c.get('role_name','')} " + " ".join(c.get("keywords", []))
        q = q.strip()
        results = retriever.search_cases(q, k=k)
        found = any(
            r.role_category == c.get("role_category") and r.role_name == c.get("role_name")
            for r in results
        )
        hit += int(found)
        print(f"  [{'✓' if found else '✗'}] {c.get('case_id')} {c.get('role_name')} "
              f"top{k}命中={found} 相似度={results[0].score if results else '-'}")

    total = len(cases)
    recall = hit / total
    print(f"\nrecall@{k} = {hit}/{total} = {recall:.2%}")
    print("提示：recall 低于 0.8 时应调检索参数（min_sim、top_k、关键词质量）或换 embedding。")
    return recall


if __name__ == "__main__":
    main()
