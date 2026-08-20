"""冒烟：一键修改简历 apply_revision 端到端（非破坏性，用临时目录）。

流程（不污染真实 data/profile.yaml 与 data/resume_latest.txt）：
  1. 用 tempfile 建临时目录，写入样例简历 + 样例分析建议（模拟 set_resume / analyze_jd 落盘）
  2. 调 apply_revision（注入临时路径）→ 打印 diff + 新简历
  3. 校验：画像已生成、备份文件已生成、新简历文本已写回
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_assistant.resume.parser import save_resume  # noqa: E402
from job_assistant.revision.apply_revision import (  # noqa: E402
    apply_revision,
    generate_revision,
)

SAMPLE_RESUME = """张三，上海财经大学金融学硕士，GPA 3.6/4.0。
实习：华泰证券研究所行研实习生6个月，独立撰写行业深度报告。
技能：Python（熟练）、Excel、Wind、SQL。
证书：证券从业资格、CET-6。
项目：新能源行业盈利预测模型，覆盖20家标的。"""

SAMPLE_ANALYSIS = {
    "role_category": "券商行研",
    "role_name": "行业研究实习生",
    "company": "华泰证券研究所",
    "match_score": 78,
    "verdict": "建议投递",
    "top_suggestions": [
        "实习经历用专业术语强化：把『独立撰写行业深度报告』扩写为『独立完成XX行业深度报告（含盈利预测模型与估值）』，点明使用 Wind 搭建财务模型。",
        "项目经历量化：补充覆盖标的数量、预测准确度或报告产出成果。",
    ],
    "strengths": ["硕士学历满足硬门槛", "有行研实习经历"],
    "gaps": [
        {"requirement": "熟练使用 Wind", "status": "satisfied", "suggestion": ""},
        {"requirement": "有行研/咨询实习经历", "status": "satisfied", "suggestion": ""},
    ],
}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_revision_"))
    resume_path = tmp / "resume_latest.txt"
    analysis_path = tmp / "last_analysis.json"
    profile_path = tmp / "profile.yaml"
    backup_dir = tmp / "backups"

    # 模拟 set_resume：解析简历 → 生成画像 + 落盘简历原文（顺带验证 parser 的 path 注入）
    save_resume(SAMPLE_RESUME, path=profile_path, resume_path=resume_path)
    analysis_path.write_text(json.dumps(SAMPLE_ANALYSIS, ensure_ascii=False), encoding="utf-8")

    print("=== 1) 前置校验：无分析 / 无简历 应友好提示（不发 LLM） ===")
    print("[无分析]", apply_revision(resume_path=resume_path, analysis_path=tmp / "nope.json", profile_path=profile_path, backup_dir=backup_dir))
    print("[无简历]", apply_revision(resume_path=tmp / "nope.txt", analysis_path=analysis_path, profile_path=profile_path, backup_dir=backup_dir))

    print("\n=== 2) generate_revision（生成 diff + 新简历，不写盘） ===")
    data = generate_revision(resume_path=resume_path, analysis_path=analysis_path)
    assert data.get("revised_resume"), "generate_revision 未返回 revised_resume"
    print("revised_resume 长度:", len(data["revised_resume"]))
    print("changes 条数:", len(data.get("changes", [])))
    for c in data.get("changes", []):
        print(f"  - [{c.get('field')}] {c.get('before')!r} -> {c.get('after')!r}")

    print("\n=== 3) apply_revision（生成 + 备份 + 写回） ===")
    out = apply_revision(resume_path=resume_path, analysis_path=analysis_path, profile_path=profile_path, backup_dir=backup_dir)
    print(out)

    print("\n=== 4) 校验 ===")
    assert profile_path.exists(), "画像未生成"
    assert resume_path.read_text(encoding="utf-8").strip(), "简历文本未写回"
    backups = list(backup_dir.glob("*")) if backup_dir.exists() else []
    assert any("resume_" in b.name for b in backups), "未生成简历备份"
    assert any("profile_" in b.name for b in backups), "未生成画像备份"
    print(f"✅ 画像已生成（{profile_path.stat().st_size} 字节）")
    print(f"✅ 简历文本已写回（{len(resume_path.read_text(encoding='utf-8'))} 字符）")
    print(f"✅ 备份文件 {len(backups)} 个：{[b.name for b in backups]}")

    print(f"\n临时目录（可手动删除）：{tmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
