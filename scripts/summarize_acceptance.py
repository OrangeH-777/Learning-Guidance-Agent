"""Summarize retained first attempts and explicit human reviews; never manufacture approvals."""

import argparse
import json
import math
from collections import Counter
from datetime import datetime

from backend.app.core.config import PROJECT_ROOT

DIMENSIONS = ("topic", "structure", "difficulty", "facts", "answer_or_relationship")
TERMINAL = {"completed", "failed", "rejected"}


def summarize(report: dict, reviews: dict | None = None) -> dict:
    definitions = json.loads(
        (PROJECT_ROOT / "tests/fixtures/acceptance_execution.json").read_text(encoding="utf-8")
    )["course_cases"]
    expected = {case["id"]: case["resource_type"] for case in definitions}
    cases = report["cases"]
    by_id = {}
    for case in cases:
        key = case["case_id"]
        if key not in expected or key in by_id or case.get("parent_task_id"):
            raise ValueError("Unknown/duplicate case or manual retry in first-attempt batch")
        if case["resource_type"] != expected[key]:
            raise ValueError("Resource type differs from approved execution set")
        by_id[key] = case

    completed = {key: case for key, case in by_id.items() if case["status"] == "completed"}
    for case in completed.values():
        if not case.get("task_id") or not case.get("resource_id"):
            raise ValueError("Completed case must identify its persisted task and resource")
        stamps = [
            datetime.fromisoformat(case[name])
            for name in ("accepted_at", "deadline_at", "finished_at")
        ]
        if any(stamp.utcoffset() is None for stamp in stamps):
            raise ValueError("Task timestamps must include their timezone")
        accepted, deadline, finished = stamps
        if not accepted <= finished <= deadline or (deadline - accepted).total_seconds() > 180:
            raise ValueError("Completed case violates its accepted deadline")

    review_by_id = {}
    if reviews is not None:
        if reviews.get("run_id") != report["run_id"]:
            raise ValueError("Human reviews belong to another run")
        for review in reviews["reviews"]:
            key = review["case_id"]
            if key not in completed or key in review_by_id:
                raise ValueError("Review must identify one successful first-attempt resource")
            if review.get("resource_id") != completed[key]["resource_id"]:
                raise ValueError("Reviewed resource does not match first attempt")
            if not all(
                isinstance(review.get(k), str) and review[k].strip()
                for k in ("reviewer", "reviewed_at", "evidence")
            ):
                raise ValueError("Human reviewer, date and evidence are required")
            datetime.fromisoformat(review["reviewed_at"])
            judgments = review.get("judgments", {})
            if set(judgments) != set(DIMENSIONS) or any(
                type(v) is not bool for v in judgments.values()
            ):
                raise ValueError("Every review dimension requires an explicit boolean judgment")
            review_by_id[key] = all(judgments.values())

    def metrics(keys):
        successful = [key for key in keys if key in completed]
        finished = all(key in by_id and by_id[key]["status"] in TERMINAL for key in keys)
        reviewed = [key for key in successful if key in review_by_id]
        human_pass = sum(review_by_id[key] for key in reviewed)
        quality_complete = bool(successful) and len(reviewed) == len(successful)
        durations = [by_id[key].get("elapsed_seconds") for key in keys if key in by_id]
        durations = [
            v for v in durations if type(v) in (int, float) and math.isfinite(v) and v >= 0
        ]
        return {
            "expected_first_attempts": len(keys),
            "recorded": sum(key in by_id for key in keys),
            "completed": len(successful),
            "batch_complete": finished,
            "first_success_rate": len(successful) / len(keys) if finished else None,
            "human_reviewed": len(reviewed),
            "human_passed": human_pass,
            "human_quality_rate": human_pass / len(successful)
            if quality_complete and finished
            else None,
            "human_quality_status": "pending_batch"
            if not finished
            else (
                "not_applicable"
                if not successful
                else ("complete" if quality_complete else "pending_review")
            ),
            "average_observed_seconds": sum(durations) / len(durations) if durations else None,
            "failures": dict(
                Counter(
                    by_id[key].get("error_code") or by_id[key]["status"]
                    for key in keys
                    if key in by_id and by_id[key]["status"] != "completed"
                )
            ),
        }

    return {
        "run_id": report["run_id"],
        "mode": report.get("mode", "unspecified"),
        "course_id": "data_structure",
        "overall": metrics(list(expected)),
        "by_type": {
            kind: metrics([key for key, value in expected.items() if value == kind])
            for kind in ("lecture", "exercise", "mindmap")
        },
        "note": (
            "First-attempt denominator is fixed. "
            "Manual retries and model verdicts are not human approval."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--reviews")
    args = parser.parse_args()
    from pathlib import Path

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    reviews = json.loads(Path(args.reviews).read_text(encoding="utf-8")) if args.reviews else None
    result = summarize(report, reviews)
    # No mutation of source records; callers may redirect the summary to their chosen file.
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
