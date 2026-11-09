import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.schemas.models import ModelFailure, ModelResponse
from backend.app.api.routes.profiles import latest_profile, profile_from_history
from backend.app.core.errors import AppError
from backend.app.db.models import (
    Course,
    ModelConfiguration,
    ProfileDraft,
    ProfileRevision,
    Resource,
    User,
)
from backend.app.schemas.business import ProfileFromHistoryInput

FIELDS = {"knowledge_base": "已接触栈", "learning_goal": "理解出栈顺序", "preference": "喜欢练习"}


@pytest.fixture
def learner():
    engine = create_engine("sqlite://")
    for entity in (Course, User, ProfileRevision, ProfileDraft, Resource, ModelConfiguration):
        entity.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = User(username="owner", password_hash="hash")
        course = Course(id="ds", name="数据结构", description="", content_version="1", enabled=True)
        db.add_all([owner, course])
        db.flush()
        db.add(
            ModelConfiguration(
                user_id=owner.id,
                version=1,
                model_id="fixture",
                encrypted_key="private-key",
                base_url="fixture",
                protocol="chat_completions",
                tested_at=datetime.now(UTC),
            )
        )
        db.commit()
        yield db, owner
    engine.dispose()


class Reply:
    def __init__(self):
        self.requests = []
        self.fields = FIELDS
        self.on_request = None

    async def generate(self, request, *, timeout_seconds):
        self.requests.append(request)
        if self.on_request:
            self.on_request()
        return ModelResponse(text=json.dumps(self.fields), model_id="fixture")

    async def run(self, learner, version=0):
        db, owner = learner
        state = SimpleNamespace(
            settings=SimpleNamespace(model_call_timeout_seconds=10),
            provider_factory=lambda config, settings: self,
        )
        request = SimpleNamespace(app=SimpleNamespace(state=state))
        return await profile_from_history(
            "ds", ProfileFromHistoryInput(expected_version=version), request, owner, db
        )


def add_resource(db, user_id, course, topic):
    db.add(
        Resource(
            user_id=user_id,
            task_id=uuid4(),
            course_id=course,
            topic=topic,
            resource_type="exercise",
            content={"title": topic, "body": "private-body"},
            source_ids=[],
            metadata_snapshot={},
        )
    )


async def test_generate_persists_complete_profile_and_scopes_evidence(learner):
    db, owner = learner
    add_resource(db, owner.id, "ds", "出栈顺序")
    add_resource(db, owner.id, "other", "private-course")
    add_resource(db, uuid4(), "ds", "private-user")
    db.add(
        ProfileDraft(
            user_id=owner.id,
            course_id="ds",
            messages=[
                {"role": "user", "content": "private-old"},
                *[{"role": "user", "content": f"练习{i}"} for i in range(8)],
                {"role": "assistant", "content": "private-assistant"},
            ],
        )
    )
    db.commit()
    reply = Reply()
    result = await reply.run(learner)
    assert result == {"version": 1, "fields": FIELDS}
    assert latest_profile(db, owner.id, "ds").fields == FIELDS
    prompt = reply.requests[0].messages[1].content
    assert "private-" not in prompt
    evidence = json.loads(prompt)
    assert evidence["recent_resources_newest_first"] == [
        {"request": "出栈顺序", "type": "exercise", "title": "出栈顺序"}
    ]
    assert len(evidence["learner_statements_oldest_first"]) == 8
    assert await reply.run(learner, version=1) == result
    assert json.loads(reply.requests[-1].messages[1].content)["confirmed_profile"] == FIELDS


async def test_history_or_output_missing_preserves_profile(learner):
    db, owner = learner
    db.add(ProfileRevision(user_id=owner.id, course_id="ds", version=1, fields=FIELDS))
    db.commit()
    reply = Reply()
    with pytest.raises(AppError, match="NO_LEARNING_HISTORY"):
        await reply.run(learner, version=1)
    assert not reply.requests
    add_resource(db, owner.id, "ds", "栈")
    db.commit()
    reply.fields = {"knowledge_base": "入门"}
    with pytest.raises(ModelFailure, match="MODEL_FORMAT"):
        await reply.run(learner, version=1)
    assert latest_profile(db, owner.id, "ds").version == 1


async def test_manual_save_during_generation_wins(learner):
    db, owner = learner
    add_resource(db, owner.id, "ds", "栈")
    db.commit()
    reply = Reply()
    manual = {**FIELDS, "learning_goal": "手动更新的目标"}

    def update_profile():
        with Session(db.get_bind()) as other:
            other.add(ProfileRevision(user_id=owner.id, course_id="ds", version=1, fields=manual))
            other.commit()

    reply.on_request = update_profile
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        await reply.run(learner)
    assert latest_profile(db, owner.id, "ds").fields == manual
