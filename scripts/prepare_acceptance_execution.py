"""Build the approved DS execution set without modifying the original imported record."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests/fixtures/acceptance_execution.json"


def build():
    baseline = json.loads(
        (ROOT / "tests/fixtures/acceptance_baseline.json").read_text(encoding="utf-8")
    )
    samples = baseline["course_cases"]
    ds13 = next(item for item in samples if item["id"] == "DS13")
    ds13["resource_type"] = "mindmap"
    ds13["request"] = "梳理二叉树层数、结点数量上界及编号约定的文本导图。"
    return {
        "baseline_sha256": baseline["source_sha256"],
        "revision": "REQ-001-approved-2026-09-27",
        "decision": "用户确认仅修订执行集DS13，原Word与原始导入记录保持不变。",
        "course_cases": samples,
    }


if __name__ == "__main__":
    TARGET.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
