"""Run approved DS01-DS30 against a real configured deployment, only by explicit invocation."""

import argparse
import getpass
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from backend.app.core.config import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--acknowledge-costs", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_costs:
        raise SystemExit(
            "This run makes billable calls. Configure an approved quota, "
            "then explicitly acknowledge costs."
        )
    cases = json.loads(
        (PROJECT_ROOT / "tests/fixtures/acceptance_execution.json").read_text(encoding="utf-8")
    )["course_cases"]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = PROJECT_ROOT / "tests/results" / f"live-{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "run_id": run_id,
        "mode": "real_configured_service",
        "expected_first_attempts": 30,
        "manual_review": "not_performed",
        "cases": [],
    }
    with httpx.Client(
        base_url=args.base_url.rstrip("/") + "/api/", timeout=15, follow_redirects=False
    ) as client:
        response = client.post(
            "auth/login",
            json={"username": args.username, "password": getpass.getpass("Password: ")},
        )
        if response.status_code != 200:
            raise SystemExit("Login failed; provider or credential details are not displayed")
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        try:
            profile = client.get("courses/data_structure/profile").json()
            model = client.get("model-settings").json()
            if not profile.get("version") or not model.get("tested_at"):
                raise SystemExit("Confirm a learning profile and test the personal model first")
            # Fixed inputs are recorded per case; failures are never removed/replaced.
            for case in cases:
                started = time.monotonic()
                entry = {
                    "case_id": case["id"],
                    "resource_type": case["resource_type"],
                    "request_key": f"{run_id}-{case['id']}",
                    "status": "not_submitted",
                    "learner_level": case["learner_level"],
                    "human_pass": None,
                }
                report["cases"].append(entry)
                output.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                try:
                    # Original cases require their learner level, not one silently reused profile.
                    updated = client.put(
                        "courses/data_structure/profile",
                        json={
                            "knowledge_base": case["learner_level"],
                            "learning_goal": case["request"],
                            "preference": "按主题提供准确的例子、前提与边界说明",
                            "expected_version": profile["version"],
                        },
                    )
                    updated.raise_for_status()
                    profile = updated.json()
                    payload = {
                        "course_id": "data_structure",
                        "topic": case["request"],
                        "resource_type": case["resource_type"],
                        "profile_version": profile["version"],
                        "model_version": model["version"],
                        "request_key": entry["request_key"],
                    }
                    accepted = client.post("tasks", json=payload)
                    if accepted.status_code != 202:
                        entry.update(status="rejected", http_status=accepted.status_code)
                    else:
                        task = accepted.json()
                        entry["task_id"] = task["id"]
                        while (
                            task["status"] not in {"completed", "failed"}
                            and time.monotonic() - started < 195
                        ):
                            time.sleep(2)
                            current = client.get("tasks/" + task["id"])
                            current.raise_for_status()
                            task = current.json()
                        entry.update(
                            status=task["status"],
                            resource_id=task.get("resource_id"),
                            error_code=task.get("error_code"),
                        )
                except httpx.HTTPError:
                    entry["status"] = "connection_error"
                finally:
                    entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
                    output.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                print(f"{case['id']}: {entry['status']}")
        finally:
            client.post("auth/logout")
    print(f"Saved {output.name}; human quality review remains required.")


if __name__ == "__main__":
    main()
