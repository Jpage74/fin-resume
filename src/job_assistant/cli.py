"""求职助手 CLI：输入一份 JD → 四环管线 → 可读报告。

用法：
    python -m job_assistant.cli --file jd.txt            # 从文件读 JD
    python -m job_assistant.cli "直接粘贴 JD 文本"        # 或直接给文本
    python -m job_assistant.cli --file jd.txt --seed     # 知识库变更后重建索引
    python -m job_assistant.cli --file jd.txt --no-save  # 不写入投递历史
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from job_assistant.analyzer.rules import GateStatus  # noqa: E402
from job_assistant.memory.history import add_application  # noqa: E402
from job_assistant.pipeline import PipelineResult, needs_proof_items, run_pipeline  # noqa: E402

_GATE_MARK = {GateStatus.PASS: "[通过]", GateStatus.FAIL: "[不满足]", GateStatus.UNKNOWN: "[待证据]"}


def _line(char: str = "=", n: int = 60) -> str:
    return char * n


def print_report(r: PipelineResult) -> None:
    reqs, report, rev = r.reqs, r.report, r.review_result

    print(_line())
    print(f"求职助手分析报告 | {reqs.role_name} @ {reqs.company or '(未写明)'} [ {reqs.role_category} ]")
    print(f"摘要：{reqs.summary}")
    print(f"来源：{reqs.source or '(未标注)'}")

    print(f"\n[1] 硬门槛校验（{len(r.gates)} 项）")
    for g in r.gates:
        print(f"  {_GATE_MARK[g.status]} {g.requirement.description} — {g.reason}")

    print(f"\n[2] 匹配岗位 & 高分案例")
    if r.retrieval.jds:
        for jd in r.retrieval.jds:
            print(f"  [岗位] {jd.role_name} @ {jd.company}  相似度 {jd.score}  source={jd.source}")
    if r.retrieval.cases:
        for c in r.retrieval.cases:
            print(f"  [案例] {c.role_name} @ {c.company}  相似度 {c.score}  source={c.source}")
    if r.retrieval.empty:
        print("  （低于相似度阈值，无匹配结果 —— 宁缺毋滥，不硬凑）")

    print(f"\n[3] 证据化差距分析 | 匹配度 {report.match_score}/100 → {report.verdict}")
    for i, g in enumerate(report.gaps, 1):
        tag = "需证据" if g.needs_proof else ("满足" if g.status == "satisfied" else "差距")
        print(f"  {i}. [{tag}] {g.requirement}")
        print(f"      {g.gap_description}")
        if g.evidence:
            print(f"      依据：{g.evidence}")
        if g.suggestion:
            print(f"      建议：{g.suggestion}")
    if report.strengths:
        print("  亮点：")
        for s in report.strengths:
            print(f"    + {s}")

    print(f"\n[4] 复核结论")
    if rev.approved:
        print("  ✅ 复核通过，结论可信，可放心参考。")
    else:
        print("  ⚠ 复核拦截：以下问题需修正后再参考 —")
        for f in rev.findings:
            if f.severity == "error":
                print(f"    ✗ [{f.item}] {f.issue}")
    for c in rev.corrections:
        print(f"    修正：{c}")

    if report.top_suggestions:
        print(f"\n[5] 简历修改建议（按优先级）")
        for i, s in enumerate(report.top_suggestions, 1):
            print(f"  {i}. {s}")

    print(_line())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="财经求职助手：JD → 完整分析报告")
    ap.add_argument("jd", nargs="?", help="JD 文本；或配合 --file 从文件读取")
    ap.add_argument("--file", help="从文件读取 JD 文本")
    ap.add_argument("--seed", action="store_true", help="先全量重建向量索引")
    ap.add_argument("--no-save", action="store_true", help="不写入投递历史")
    ap.add_argument("--source", default="", help="JD 来源标识（渠道+编号），用于溯源与去重")
    args = ap.parse_args(argv)

    if args.file:
        jd_text = Path(args.file).read_text(encoding="utf-8")
        source = args.source or args.file
    elif args.jd:
        jd_text = args.jd
        source = args.source
    else:
        ap.error("需要提供 JD：--file 指定文件，或直接传入 JD 文本")
        return 2

    try:
        result = run_pipeline(jd_text, source=source, seed_index=args.seed)
    except Exception as e:
        print(f"分析失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print_report(result)

    if not args.no_save:
        add_application(
            jd_id=result.reqs.source or result.reqs.role_name,
            company=result.reqs.company or "",
            role=result.reqs.role_name,
            status="analyzed",
            match_score=result.report.match_score,
            needs_proof_items=json.dumps(needs_proof_items(result.report), ensure_ascii=False),
        )
        print("(已记录到投递历史 data/history.db)")

    if not result.review_result.approved:
        print("提示：复核未通过，输出仅供参考，请按修正建议核对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
