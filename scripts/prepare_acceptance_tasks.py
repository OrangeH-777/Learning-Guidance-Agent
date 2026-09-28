"""Build executable acceptance task cards without claiming that any case has passed."""

import argparse
import json

import yaml

from backend.app.core.config import PROJECT_ROOT

# These checks support the task; they do not replace its exact steps or live/manual review.
CHECK_GROUPS = [
    (
        1,
        6,
        ["tests/contract/test_input_contracts.py", "tests/integration/test_accounts_profiles.py"],
    ),
    (
        7,
        14,
        ["tests/contract/test_input_contracts.py", "tests/integration/test_generation_flow.py"],
    ),
    (15, 20, ["tests/integration/test_generation_flow.py"]),
    (21, 28, ["tests/contract/test_resource_contracts.py", "tests/unit/test_learning_workflow.py"]),
    (29, 39, ["tests/unit/test_task_runtime.py", "tests/integration/test_executor_failures.py"]),
    (40, 43, ["tests/integration/test_task_reliability.py"]),
    (
        44,
        47,
        [
            "tests/integration/test_accounts_profiles.py",
            "tests/integration/test_output_security.py",
        ],
    ),
    (48, 51, ["tests/integration/test_task_reliability.py", "tests/integration/test_load.py"]),
    (
        52,
        56,
        [
            "tests/unit/test_fact_and_security.py",
            "tests/unit/test_learning_workflow.py",
            "tests/integration/test_output_security.py",
        ],
    ),
]
LIVE_CASES = {7, 8, 14, 17, 18, 20, 21, 22, 23, 25, 27, 55, 59, 60}


def build_tasks():
    fixture = PROJECT_ROOT / "tests/fixtures"
    baseline = json.loads((fixture / "acceptance_baseline.json").read_text(encoding="utf-8"))
    revised = json.loads((fixture / "acceptance_execution.json").read_text(encoding="utf-8"))
    tasks = []
    for kind, cases in (
        ("integration", baseline["integration_cases"]),
        ("system", baseline["system_cases"]),
        ("course", revised["course_cases"]),
    ):
        for case in cases:
            number = int(case["id"][2:])
            checks = []
            if kind == "system":
                checks = [
                    path
                    for low, high, paths in CHECK_GROUPS
                    if low <= number <= high
                    for path in paths
                ]
            elif kind == "integration":
                checks = ["tests/integration"]
            requirements = ["独立测试账号与数据库；记录执行环境；禁止使用私人资料"]
            if (
                kind == "course"
                or (kind == "system" and number in LIVE_CASES)
                or case["id"] == "IT04"
            ):
                requirements.append("实际模型、嵌入配置和费用额度；材料完成复核；不能用替身代替")
            if case["id"] in {"TC057", "TC058", "TC060"} or kind == "course":
                requirements.append("实际执行人/复核者及可追溯证据；助手不能代签")
            commands = ["uv run --locked pytest -q " + " ".join(checks)] if checks else []
            if case["id"] in {"TC030", "TC032", "TC046", "TC057"}:
                commands.append("cd frontend; npm run test:e2e")
            if kind == "course":
                requirements.append("使用TC059同一批次中的对应首次任务；不要为每张DS卡重复运行整批")
            if case["id"] == "TC059":
                commands.append(
                    "uv run --locked python -m scripts.run_course_acceptance "
                    "--username YOUR_TEST_USER --acknowledge-costs"
                )
            tasks.append(
                {
                    "id": case["id"],
                    "kind": kind,
                    "specification": {
                        key: value for key, value in case.items() if key != "execution_status"
                    },
                    "prerequisites": requirements,
                    "supporting_commands": commands,
                    "steps": [
                        "按specification中的全部输入逐值执行，记录实际结果；支持性测试不自动代替此步骤。",
                        "逐项比对expected；DS按request、expected_points及原始评分规则复核。",
                        "记录失败、task_id与证据；重试追加记录，不替换首次结果。",
                    ],
                    "execution_status": "not_run",
                    "record_fields": [
                        "executor",
                        "executed_at",
                        "environment",
                        "task_id",
                        "actual_result",
                        "evidence",
                        "reviewer",
                        "defects",
                    ],
                }
            )
    return {
        "schema_version": 1,
        "original_source_sha256": baseline["source_sha256"],
        "note": "执行任务定义；非运行报告。DS13采用已确认修订；原始规格保持不变。",
        "tasks": tasks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = PROJECT_ROOT / "tests/acceptance/tasks.yaml"
    content = build_tasks()
    if args.check:
        if not target.exists() or yaml.safe_load(target.read_text(encoding="utf-8")) != content:
            raise SystemExit("Acceptance task cards are missing or stale")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    print(f"Acceptance tasks: {len(content['tasks'])}; no execution results fabricated")


if __name__ == "__main__":
    main()
