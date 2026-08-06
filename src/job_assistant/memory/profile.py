"""用户画像记忆（极简版）。

MVP 用 profile.yaml 单文件持久化；后续可升级 ADK 记忆 API / 数据库。
注意：profile.yaml 含真实个人信息，已在 .gitignore 排除。
"""
from pathlib import Path

import yaml

PROFILE_PATH = Path(__file__).resolve().parents[3] / "data" / "profile.yaml"

DEFAULT_PROFILE = {
    "user": {
        "name": "",
        "school": "",
        "major": "",
        "degree": "",
        "gpa": "",
        "target_roles": [],
        "target_city": [],
        "constraints": [],
        "skills": [],
        "certs": [],
        "internships": [],   # 实习经历（evidence_key: internships>=N 用它计数）
        "projects": [],
    }
}


def load_profile(path: Path = PROFILE_PATH) -> dict:
    if not path.exists():
        return DEFAULT_PROFILE
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or DEFAULT_PROFILE


def save_profile(profile: dict, path: Path = PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile, f, allow_unicode=True, sort_keys=False)
