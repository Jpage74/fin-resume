"""案例检索子 agent：JobRequirements → 匹配岗位 + 高分案例（带 source）。

RAG 实现：Chroma 向量库 + fastembed 中文 embedding（bge-small-zh）。
防幻觉检索参数（设计文档六.2）：
- top_k 小（MVP 默认 3）
- 相似度阈值：低于阈值的结果丢弃，宁缺毋滥
- 结果必须带 source，可溯源
检索参数与生成参数分离——低温只保证生成不飘，检索质量由 top_k / 阈值保证。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from job_assistant.paths import CHROMA_DIR  # noqa: E402
from job_assistant.retriever.embedder import Embedder  # noqa: E402
from job_assistant.schemas import JobRequirements  # noqa: E402

# 默认检索参数：top_k 小 + 相似度阈值低门槛（宁缺毋滥）
DEFAULT_K = 3
DEFAULT_MIN_SIM = 0.4  # 余弦相似度下限；低于它判定「不相关」不返回


@dataclass
class RetrievedDoc:
    doc_id: str
    role_category: str
    role_name: str
    source: str
    score: float  # 余弦相似度 0~1
    content: str = ""  # 原文，供下游引用
    company: str | None = None


@dataclass
class RetrievalResult:
    jds: list[RetrievedDoc] = field(default_factory=list)
    cases: list[RetrievedDoc] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.jds and not self.cases


class CaseRetriever:
    """封装 Chroma 两个集合：jds（岗位库）、cases（高分案例库）。"""

    def __init__(self, chroma_dir: Path = CHROMA_DIR, embedder: Embedder | None = None):
        import chromadb  # 延迟导入：缺失时给清晰报错而不是栈崩

        self.embedder = embedder or Embedder()
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._jds = self._client.get_or_create_collection(
            name="jds", metadata={"hnsw:space": "cosine"}
        )
        self._cases = self._client.get_or_create_collection(
            name="cases", metadata={"hnsw:space": "cosine"}
        )

    # ---- 索引 ----

    def add_jd(self, doc: dict) -> None:
        self._add(self._jds, doc)

    def add_case(self, doc: dict) -> None:
        self._add(self._cases, doc)

    def _add(self, coll, doc: dict) -> None:
        """doc: {id, text, source, role_category, role_name, company}"""
        emb = self.embedder.embed_texts([doc["text"]])
        coll.upsert(
            ids=[doc["id"]],
            documents=[doc["text"]],
            embeddings=emb,
            metadatas=[
                {
                    "source": doc.get("source", ""),
                    "role_category": doc.get("role_category", ""),
                    "role_name": doc.get("role_name", ""),
                    "company": doc.get("company", "") or "",
                }
            ],
        )

    def reset(self) -> None:
        for name in ("jds", "cases"):
            try:
                self._client.delete_collection(name)
            except Exception:
                pass
        self._jds = self._client.get_or_create_collection(
            name="jds", metadata={"hnsw:space": "cosine"}
        )
        self._cases = self._client.get_or_create_collection(
            name="cases", metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> dict:
        return {"jds": self._jds.count(), "cases": self._cases.count()}

    # ---- 检索 ----

    def retrieve(
        self, reqs: JobRequirements, k: int = DEFAULT_K, min_sim: float = DEFAULT_MIN_SIM
    ) -> RetrievalResult:
        """输入标准化 JobRequirements，返回匹配岗位 + 高分案例。

        低于相似度阈值的结果丢弃；全部低于阈值 → 返回空（不硬凑，防幻觉）。
        """
        q_vec = self.embedder.embed_query(self._build_query(reqs))
        return RetrievalResult(
            jds=[self._hit(r, doc, meta) for r, doc, meta in self._query(self._jds, q_vec, k, min_sim)],
            cases=[self._hit(r, doc, meta) for r, doc, meta in self._query(self._cases, q_vec, k, min_sim)],
        )

    def search_cases(
        self, query_text: str, k: int = DEFAULT_K, min_sim: float = DEFAULT_MIN_SIM
    ) -> list[RetrievedDoc]:
        """按任意文本直接检索高分案例（RAG 评测、后续联网搜索入口用）。"""
        q_vec = self.embedder.embed_query(query_text)
        return [
            self._hit(sim, doc, meta)
            for sim, doc, meta in self._query(self._cases, q_vec, k, min_sim)
        ]

    def _query(self, coll, q_vec, k: int, min_sim: float):
        res = coll.query(query_embeddings=[q_vec], n_results=max(k * 4, 5))
        hits = []
        for i in range(len(res["ids"][0])):
            dist = res["distances"][0][i]
            sim = 1.0 - dist  # cosine 距离 → 相似度
            if sim < min_sim:
                continue  # 低于阈值：不相关，丢弃
            hits.append((sim, res["documents"][0][i], res["metadatas"][0][i]))
        hits.sort(key=lambda h: h[0], reverse=True)
        return hits[:k]

    @staticmethod
    def _hit(sim, doc, meta) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id="",  # ids 未透传，由 source 溯源
            role_category=meta.get("role_category", ""),
            role_name=meta.get("role_name", ""),
            source=meta.get("source", ""),
            company=meta.get("company") or None,
            score=round(sim, 4),
            content=doc,
        )

    @staticmethod
    def _build_query(reqs: JobRequirements) -> str:
        parts = [reqs.role_category, reqs.role_name]
        if reqs.company:
            parts.append(reqs.company)
        parts += [r.description for r in reqs.hard_requirements]
        parts += [r.description for r in reqs.soft_requirements]
        parts += [r.description for r in reqs.bonus_requirements]
        return " ".join(p for p in parts if p)
