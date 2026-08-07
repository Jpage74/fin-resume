"""种子库导入：data/knowledge/{cases,jds}/**/*.yaml → Chroma 向量库。

设计文档原则「种子库保质量」：MVP 用手工精选案例保证质量，
自动收集（增强 2）的抓取结果先进 candidates 表，审核后才入库。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from job_assistant.paths import KNOWLEDGE_DIR  # noqa: E402
from job_assistant.retriever.case_retriever import CaseRetriever  # noqa: E402


def case_document(d: dict) -> str:
    """把结构化案例拍平成可检索文本（检索是纯文本语义匹配）。

    素材形态是「背景画像」（bg 帖/公开面经），不是完整简历：
    resume 下字段大多可缺省（bg 帖常没有 gpa / projects），缺省留空即可。
    bg / result 保留原始自述与结果，检索时也纳入文本。
    """
    r = d.get("resume", {})
    parts = [
        f"[{d.get('role_category', '')}] {d.get('role_name', '')} 背景画像案例",
        f"公司：{d.get('company', '')}",
        f"背景自述：{d.get('bg', '')}",
        f"结果：{d.get('result', '')}",
        f"学历：{r.get('school', '')} {r.get('degree', '')} {r.get('major', '')} 绩点{r.get('gpa', '')}",
        "技能：" + "、".join(r.get("skills") or []),
        "证书：" + "、".join(r.get("certs") or []),
        "实习：" + "；".join(r.get("internships") or []),
        "项目：" + "；".join(f"{p.get('name', '')}：{p.get('detail', '')}" for p in r.get("projects") or []),
        "关键词：" + "、".join(d.get("keywords") or []),
    ]
    return "\n".join(p for p in parts if p and not p.endswith("："))


def jd_document(d: dict) -> str:
    """JD 条目 → 检索文本（优先用原文 jd_text）。"""
    if d.get("jd_text"):
        return d["jd_text"]
    parts = [
        f"[{d.get('role_category', '')}] {d.get('role_name', '')}",
        f"公司：{d.get('company', '')}",
        f"摘要：{d.get('summary', '')}",
    ]
    return "\n".join(p for p in parts if p and not p.endswith("："))


def load_yaml_docs(kind: str) -> list[dict]:
    """读 data/knowledge/{kind}/**/*.yaml → 条目列表（kind: cases | jds）。"""
    root = KNOWLEDGE_DIR / kind
    docs = []
    if not root.exists():
        return docs
    for p in sorted(root.rglob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:  # 单个坏文件不阻断整体
            print(f"  ! 跳过 {p.name}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        data["_path"] = str(p)
        docs.append(data)
    return docs


def build_index(retriever: CaseRetriever, verbose: bool = True) -> dict:
    """全量重建索引：读种子库 → 向量化 → upsert。返回索引计数。"""
    if verbose:
        print("读取知识库 …")
    n_jd = n_case = 0
    for d in load_yaml_docs("jds"):
        retriever.add_jd(
            {
                "id": d.get("jd_id", str(d["_path"])),
                "text": jd_document(d),
                "source": d.get("source", ""),
                "role_category": d.get("role_category", ""),
                "role_name": d.get("role_name", ""),
                "company": d.get("company", ""),
            }
        )
        n_jd += 1
    for d in load_yaml_docs("cases"):
        retriever.add_case(
            {
                "id": d.get("case_id", str(d["_path"])),
                "text": case_document(d),
                "source": d.get("source", ""),
                "role_category": d.get("role_category", ""),
                "role_name": d.get("role_name", ""),
                "company": d.get("company", ""),
            }
        )
        n_case += 1
    if verbose:
        print(f"  导入 JD {n_jd} 条，案例 {n_case} 条")
    return {"jds": n_jd, "cases": n_case}


if __name__ == "__main__":
    # 冒烟：全量建索引并打印计数
    r = CaseRetriever()
    build_index(r)
    print("向量库计数:", r.count())
