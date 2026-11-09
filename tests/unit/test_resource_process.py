import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.api.routes.resources import resource
from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask, Resource, User, ValidationRecord
from backend.app.schemas.responses import ResourceResponse


@pytest.mark.parametrize("legacy", [False, True])
def test_resource_process_uses_the_owned_tasks_published_attempt(legacy):
    engine = create_engine("sqlite://")
    for entity in (GenerationTask, Resource, ValidationRecord):
        entity.__table__.create(engine)
    owner = User(id=uuid4())
    content = json.loads(
        (Path(__file__).parents[1] / "fixtures/resource_contracts.json").read_text(encoding="utf8")
    )["resources"][0]
    profile = dict(knowledge_base="入门", learning_goal="学栈", preference="举例")
    model_id = uuid4()
    metadata = dict(
        profile={**profile, "version": 1},
        model=dict(
            protocol="responses",
            model_id="demo",
            configuration_version=1,
            configuration_id=str(model_id),
        ),
        prompt_version="p1",
        knowledge_version="k1",
        ai_notice="由AI生成，仅供参考",
        automatic_checks="passed",
        human_pass=False,
    )
    if not legacy:
        metadata["planning"] = dict(objectives=["能判断出栈顺序"], outline=["入栈", "出栈"])
    with Session(engine) as db:
        task = GenerationTask(
            user_id=owner.id,
            model_configuration_id=model_id,
            course_id="course",
            topic="栈",
            resource_type="lecture",
            status="completed",
            request_key="key",
            request_digest="digest",
            profile_version=1,
            profile_snapshot=profile,
            knowledge_version="k1",
            prompt_version="p1",
            deadline_at=datetime.now(UTC),
            chapter_snapshot=None if legacy else {"title": "第二章 栈", "content": "private-body"},
            content_regenerations=1,
        )
        db.add(task)
        db.flush()
        row = Resource(
            user_id=owner.id,
            task_id=task.id,
            course_id="course",
            topic="栈",
            resource_type="lecture",
            content=content,
            source_ids=content["source_ids"],
            metadata_snapshot=metadata,
        )
        db.add_all(
            [
                row,
                ValidationRecord(task_id=task.id, attempt=0, passed=False, checks={"safe": True}),
                ValidationRecord(
                    task_id=task.id,
                    attempt=1,
                    passed=True,
                    checks={"relevant": True, "secret": True},
                ),
            ]
        )
        if not legacy:
            db.add(
                ValidationRecord(
                    task_id=task.id,
                    attempt=1,
                    passed=True,
                    checks={"final": True, "unchanged": True},
                )
            )
        db.flush()
        payload = ResourceResponse.model_validate(resource(row.id, owner, db))
        result = payload.process
        assert result.chapter == (None if legacy else "第二章 栈")
        assert result.regenerations == 1
        assert result.passed_checks == ["relevant"]
        assert result.format_unchanged is (None if legacy else True)
        if legacy:
            assert result.planning is None
        else:
            assert result.planning.outline == ["入栈", "出栈"]
            assert result.planning.objectives == ["能判断出栈顺序"]
        assert "private-body" not in payload.model_dump_json()
        with pytest.raises(AppError) as error:
            resource(row.id, User(id=uuid4()), db)
        assert error.value.status == 404

