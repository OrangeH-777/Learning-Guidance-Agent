"""Verify source fidelity and coverage, not execution of business acceptance cases."""

import json
from collections import Counter

from scripts.import_acceptance_baseline import TARGET, build_baseline


def test_fixture_matches_the_original_document():
    assert json.loads(TARGET.read_text(encoding="utf-8")) == build_baseline()


def test_every_system_case_has_exactly_one_source_scenario():
    baseline = build_baseline()
    covered = [case for row in baseline["traceability"] for case in row["case_ids"]]
    assert Counter(covered) == Counter(case["id"] for case in baseline["system_cases"])


def test_original_distribution_and_execution_status_are_preserved():
    baseline = build_baseline()
    # The source claims 10/10/10, but its table actually contains 10/11/9.
    # Keep the source immutable; an approved execution-set amendment is separate.
    assert Counter(case["resource_type"] for case in baseline["course_cases"]) == {
        "lecture": 10,
        "exercise": 11,
        "mindmap": 9,
    }
    for group in ("integration_cases", "system_cases", "course_cases"):
        assert all(case["execution_status"] == "not_run" for case in baseline[group])
