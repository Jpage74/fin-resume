"""硬门槛规则校验：JobRequirements × 用户画像 → 逐条校验结果。

把每条硬门槛的 evidence_key 翻译成画像里的证据并判定：
    PASS    — 画像证据明确满足
    FAIL    — 画像证据明确不满足
    UNKNOWN — 画像里没有对应证据 → needs_proof（宁可标记未知，不默认通过）

防幻觉原则（设计文档六）：无证据的结论一律标记 needs_proof。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from job_assistant.schemas import JobRequirements, Requirement


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # 画像无对应证据 → needs_proof


@dataclass
class GateResult:
    requirement: Requirement
    status: GateStatus
    reason: str  # 判定依据 / 缺什么证据


# 学历层级（用于 >= 比较）
_DEGREE_TIER = {"博士": 4, "硕士": 3, "本科": 2, "专科": 1}


def resolve_evidence(profile: dict, evidence_key: str) -> tuple[bool, bool]:
    """把 evidence_key 映射到画像证据。

    Returns:
        (resolved, satisfied):
            resolved=False → 画像里没有该证据（调用方标记 UNKNOWN）；
            resolved=True  → 画像可判定，satisfied 为是否满足。
    """
    user = profile.get("user", {})

    if evidence_key.startswith("degree>="):
        need = _DEGREE_TIER.get(evidence_key.split(">=")[1], 0)
        degree = (user.get("degree") or "").strip()
        if not degree:
            return False, False
        have = 0
        for name, tier in _DEGREE_TIER.items():
            if name in degree:
                have = max(have, tier)
        return True, have >= need

    if evidence_key.startswith("cert:"):
        name = evidence_key.split(":", 1)[1].lower()
        certs = user.get("certs") or []
        if not certs:
            return False, False
        return True, name in " ".join(str(c).lower() for c in certs)

    if evidence_key.startswith("skill:"):
        name = evidence_key.split(":", 1)[1].lower()
        skills = user.get("skills") or []
        if not skills:
            return False, False
        names = " ".join((s.get("name") or "").lower() for s in skills)
        return True, name in names

    if evidence_key.startswith("internships>="):
        n = float(evidence_key.split(">=")[1])
        internships = user.get("internships") or []
        if not internships:
            return False, False
        return True, len(internships) >= n

    if evidence_key.startswith("gpa>="):
        need = float(evidence_key.split(">=")[1])
        gpa = (user.get("gpa") or "").strip()
        if not gpa:
            return False, False
        try:
            return True, float(gpa) >= need
        except ValueError:
            return False, False

    return False, False


def validate_hard_gates(reqs: JobRequirements, profile: dict) -> list[GateResult]:
    """对全部硬门槛逐条判定。"""
    results = []
    for r in reqs.hard_requirements:
        resolved, satisfied = resolve_evidence(profile, r.evidence_key)
        if not resolved:
            results.append(
                GateResult(
                    r,
                    GateStatus.UNKNOWN,
                    reason=f"画像缺少证据 evidence[{r.evidence_key}]，需补充（needs_proof）",
                )
            )
        elif satisfied:
            results.append(
                GateResult(r, GateStatus.PASS, reason=f"evidence[{r.evidence_key}] 满足（{r.verdict_rule}）")
            )
        else:
            results.append(
                GateResult(r, GateStatus.FAIL, reason=f"evidence[{r.evidence_key}] 不满足（{r.verdict_rule}）")
            )
    return results


def gate_summary(results: list[GateResult]) -> dict:
    """汇总：pass / fail / unknown 计数。"""
    counts = {s.value: 0 for s in GateStatus}
    for r in results:
        counts[r.status.value] += 1
    counts["total"] = len(results)
    counts["blocked"] = counts[GateStatus.FAIL.value]  # 有 FAIL 则提示先别投
    return counts
