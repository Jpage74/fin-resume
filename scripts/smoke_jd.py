"""冒烟：jd_analyzer 解析 JD → JobRequirements → 硬门槛规则校验。

验证管线第一环端到端：
  真实 JD 文本 → LLM 抽取结构化需求 → Pydantic 校验 → 用户画像硬门槛判定。
"""
import json
import sys
from pathlib import Path

# Windows 控制台默认 GBK：强制 UTF-8，避免中文乱码 / emoji 编码报错
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.analyzer.jd_analyzer import analyze_jd  # noqa: E402
from job_assistant.analyzer.rules import gate_summary, validate_hard_gates  # noqa: E402
from job_assistant.memory.profile import load_profile  # noqa: E402

SAMPLE_JD = """公司：华泰证券研究所
岗位：行业研究实习生（消费方向）
【学历要求】重点院校硕士在读，2027 届优先；
【证书要求】有证券从业资格证者优先；
【技能要求】熟练使用 Excel、Wind，掌握 Python 或 R 者加分；
【实习要求】有券商研究所实习经历者优先；
【其他】每周实习 4 天以上，至少实习 3 个月，有较强的抗压能力与文字功底。"""


def main():
    print("=== 1) 解析 JD ===")
    reqs = analyze_jd(SAMPLE_JD, source="smoke:华泰行研实习")
    print(json.dumps(json.loads(reqs.model_dump_json()), ensure_ascii=False, indent=2))

    print("\n=== 2) 硬门槛校验（对当前画像） ===")
    profile = load_profile()
    gates = validate_hard_gates(reqs, profile)
    for g in gates:
        mark = {"pass": "[通过]", "fail": "[不满足]", "unknown": "[需证据]"}[g.status.value]
        print(f"  {mark} [{g.status.value}] {g.requirement.description} — {g.reason}")
    print("  汇总:", gate_summary(gates))


if __name__ == "__main__":
    main()
