import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.app.core.config import PROJECT_ROOT
from backend.app.db.models import GenerationTask, ModelConfiguration, Resource
from tests.integration.conftest import register


def test_ten_sessions_hundred_resources_hundred_non_generation_requests(client, app, test_engine):
    clients = []
    for index in range(10):
        browser = TestClient(app)
        identity = register(browser, f"load_user_{index}")["user"]["id"]
        clients.append(browser)
        with Session(test_engine) as db, db.begin():
            from uuid import UUID

            owner = UUID(identity)
            model = ModelConfiguration(
                user_id=owner,
                version=1,
                protocol="responses",
                base_url="https://fixture.invalid",
                model_id="fixture",
                encrypted_key="fixture",
            )
            db.add(model)
            db.flush()
            for _ in range(10):
                task = GenerationTask(
                    user_id=owner,
                    course_id="data_structure",
                    request_key=str(uuid4()),
                    request_digest="a" * 64,
                    status="completed",
                    topic="栈",
                    resource_type="lecture",
                    profile_version=1,
                    profile_snapshot={},
                    model_configuration_id=model.id,
                    knowledge_version="fixture",
                    prompt_version="fixture",
                    deadline_at=datetime.now(UTC),
                )
                db.add(task)
                db.flush()
                db.add(
                    Resource(
                        user_id=owner,
                        task_id=task.id,
                        course_id=task.course_id,
                        topic=task.topic,
                        resource_type="lecture",
                        content={"title": "fixture"},
                        metadata_snapshot={},
                        source_ids=[],
                    )
                )

    def requests(browser):
        results = []
        profile_version = 0
        for index in range(10):
            start = time.perf_counter()
            if index % 3 == 2:
                response = browser.put(
                    "/api/courses/data_structure/profile",
                    json={
                        "knowledge_base": "已有数组基础",
                        "learning_goal": f"学习栈{index}",
                        "preference": "示例",
                        "expected_version": profile_version,
                    },
                )
                if response.status_code == 200:
                    profile_version = response.json()["version"]
            else:
                response = browser.get("/api/resources" if index % 2 else "/api/courses")
            results.append((time.perf_counter() - start, response.status_code))
        return results

    engine = app.state.database_engine
    lock = Lock()
    checked_out = engine.pool.checkedout()
    peak_connections = checked_out

    def checkout(*args):
        nonlocal checked_out, peak_connections
        with lock:
            checked_out += 1
            peak_connections = max(peak_connections, checked_out)

    def checkin(*args):
        nonlocal checked_out
        with lock:
            checked_out -= 1

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)
    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = [item for group in pool.map(requests, clients) for item in group]
    finally:
        event.remove(engine, "checkout", checkout)
        event.remove(engine, "checkin", checkin)
    latencies = sorted(seconds for seconds, _ in results)
    errors = sum(status >= 500 for _, status in results)
    report = {
        "transport": "FastAPI TestClient/ASGI, not remote HTTP",
        "database": "real PostgreSQL",
        "sessions": 10,
        "resources": 100,
        "requests": len(results),
        "concurrency": 10,
        "p95_seconds": latencies[math.ceil(0.95 * len(latencies)) - 1],
        "server_errors": errors,
        "model_calls": 0,
        "query_requests": 70,
        "profile_write_requests": 30,
        "peak_database_connections_including_scheduler": peak_connections,
        "connections_after_requests": engine.pool.checkedout(),
        "pool_size": engine.pool.size(),
    }
    target = PROJECT_ROOT / "tests/results/load.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert len(results) == 100 and all(status == 200 for _, status in results)
    assert errors == 0 and report["p95_seconds"] <= 2
    assert peak_connections <= 11 and engine.pool.checkedout() == 1
