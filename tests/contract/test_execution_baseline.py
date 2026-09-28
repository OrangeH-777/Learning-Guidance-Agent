import json
from collections import Counter

from scripts.prepare_acceptance_execution import TARGET, build


def test_approved_execution_set_preserves_ids_and_balances_types():
    data = json.loads(TARGET.read_text(encoding="utf-8"))
    assert data == build()
    assert [item["id"] for item in data["course_cases"]] == [f"DS{i:02}" for i in range(1, 31)]
    assert Counter(item["resource_type"] for item in data["course_cases"]) == {
        "lecture": 10,
        "exercise": 10,
        "mindmap": 10,
    }
    assert all(item["execution_status"] == "not_run" for item in data["course_cases"])
