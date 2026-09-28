import yaml

from backend.app.core.config import PROJECT_ROOT
from scripts.prepare_acceptance_tasks import build_tasks


def test_all_original_cases_have_reproducible_executable_task_cards():
    tasks = build_tasks()
    saved = yaml.safe_load(
        (PROJECT_ROOT / "tests/acceptance/tasks.yaml").read_text(encoding="utf-8")
    )
    assert saved == tasks
    ids = [row["id"] for row in tasks["tasks"]]
    assert len(ids) == len(set(ids)) == 98
    assert all(row["execution_status"] == "not_run" for row in tasks["tasks"])
    assert all(row["steps"] and row["prerequisites"] for row in tasks["tasks"])
