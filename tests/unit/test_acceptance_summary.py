import json
from copy import deepcopy

import pytest

from backend.app.core.config import PROJECT_ROOT
from scripts.summarize_acceptance import DIMENSIONS, summarize


def batch():
    cases = json.loads(
        (PROJECT_ROOT / "tests/fixtures/acceptance_execution.json").read_text(encoding="utf-8")
    )["course_cases"]
    return {
        "run_id": "fixture-only",
        "mode": "test_fixture",
        "cases": [
            {
                "case_id": case["id"],
                "resource_type": case["resource_type"],
                "status": "failed",
                "error_code": "CONTENT_REJECTED",
                "elapsed_seconds": 1,
            }
            for case in cases
        ],
    }


def completed(report, count):
    for case in report["cases"][:count]:
        case.update(
            status="completed",
            task_id=case["case_id"],
            resource_id="resource-" + case["case_id"],
            accepted_at="2026-09-28T00:00:00+00:00",
            deadline_at="2026-09-28T00:03:00+00:00",
            finished_at="2026-09-28T00:00:30+00:00",
            human_pass=True,
        )


def test_fixed_denominator_type_splits_and_no_automatic_human_approval():
    report = batch()
    completed(report, 27)
    result = summarize(report)
    assert result["mode"] == "test_fixture"
    assert result["overall"]["first_success_rate"] == 0.9
    assert result["overall"]["human_quality_rate"] is None
    assert result["overall"]["human_reviewed"] == 0
    assert all(item["expected_first_attempts"] == 10 for item in result["by_type"].values())


def test_incomplete_or_disconnected_batch_has_no_final_rate():
    report = batch()
    report["cases"].pop()
    assert summarize(report)["overall"]["first_success_rate"] is None
    report = batch()
    report["cases"][0]["status"] = "connection_error"
    assert summarize(report)["overall"]["first_success_rate"] is None


def test_zero_success_quality_is_not_applicable():
    result = summarize(batch())["overall"]
    assert result["first_success_rate"] == 0
    assert result["human_quality_rate"] is None
    assert result["human_quality_status"] == "not_applicable"


@pytest.mark.parametrize("mutation", ["duplicate", "retry", "wrong_type", "late"])
def test_invalid_first_attempt_records_are_rejected(mutation):
    report = batch()
    completed(report, 1)
    if mutation == "duplicate":
        report["cases"].append(deepcopy(report["cases"][0]))
    elif mutation == "retry":
        report["cases"][0]["parent_task_id"] = "original-task"
    elif mutation == "wrong_type":
        report["cases"][0]["resource_type"] = "video"
    else:
        report["cases"][0]["finished_at"] = "2026-09-28T00:03:01+00:00"
    with pytest.raises(ValueError):
        summarize(report)


def test_explicit_review_evidence_and_all_dimensions_are_required():
    report = batch()
    completed(report, 2)
    reviews = {
        "run_id": "fixture-only",
        "reviews": [
            {
                "case_id": c["case_id"],
                "resource_id": c["resource_id"],
                "reviewer": "test-only reviewer",
                "reviewed_at": "2026-09-28",
                "evidence": "fixture-only evidence, not a real review",
                "judgments": dict.fromkeys(DIMENSIONS, True),
            }
            for c in report["cases"][:2]
        ],
    }
    reviews["reviews"][1]["judgments"]["facts"] = False
    assert summarize(report, reviews)["overall"]["human_quality_rate"] == 0.5
    reviews["reviews"][0]["evidence"] = ""
    with pytest.raises(ValueError):
        summarize(report, reviews)
