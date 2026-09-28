import json
from pathlib import Path
from uuid import uuid4

import pytest

from agents.schemas.models import ModelSelection
from agents.schemas.workflow import (
    ContentVerdict,
    ProfileSnapshot,
    ResourcePlan,
    SourceFragment,
    WorkflowInput,
)
from agents.workflows.learning import ContentRejected, WorkflowNodes, run_workflow
from agents.workflows.runtime import Deadline

RESOURCES = json.loads(
    (Path(__file__).parents[1] / "fixtures/resource_contracts.json").read_text(encoding="utf-8")
)["resources"]


def build_nodes(
    resource, *, bad_candidates=0, wrong_source=False, corrupt_format=False, verifier_crashes=False
):
    user_id, source_id = uuid4(), uuid4()
    context = WorkflowInput(
        task_id=uuid4(),
        user_id=user_id,
        course_id="data_structure",
        topic="栈",
        resource_type=resource["resource_type"],
        knowledge_version="test-v1",
        prompt_version="test-v1",
        profile=ProfileSnapshot(
            version=1, knowledge_base="初学", learning_goal="理解栈", preference="例子"
        ),
        model=ModelSelection(
            configuration_id="fixture",
            configuration_version=1,
            protocol="responses",
            model_id="test-model",
        ),
    )
    candidate = {**resource, "source_ids": [str(source_id)]}
    stages, checks, calls = [], [], []

    async def retrieve(ctx):
        return (
            SourceFragment(
                id=source_id,
                course_id="other" if wrong_source else "data_structure",
                visibility="public",
                owner_id=None,
                content="fixture only",
                locator="fixture",
                index_version="test-v1",
            ),
        )

    async def plan(ctx, sources):
        return ResourcePlan(
            objectives=("理解栈",),
            difficulty="入门",
            prerequisites=("序列",),
            outline=("栈",),
            personalization="用例子理解",
        )

    async def generate(ctx, plan, sources, feedback):
        calls.append(feedback)
        return {} if len(calls) <= bad_candidates else candidate

    async def verify(ctx, resource, sources):
        if verifier_crashes:
            raise RuntimeError("verification unavailable")
        return ContentVerdict(
            relevant=True, supported=True, facts_correct=True, answers_consistent=True, safe=True
        )

    async def format_output(resource):
        result = resource.model_dump(mode="json")
        if corrupt_format:
            result["source_ids"] = [str(uuid4())]
        return result

    async def stage(name):
        stages.append(name)

    async def record(attempt, passed, details):
        checks.append((attempt, passed, details))

    return (
        context,
        WorkflowNodes(retrieve, plan, generate, verify, format_output, stage, record),
        stages,
        checks,
        calls,
    )


@pytest.mark.parametrize("resource", RESOURCES, ids=["lecture", "exercise", "mindmap"])
async def test_three_resource_types_pass_only_after_final_verification(resource):
    context, nodes, stages, checks, calls = build_nodes(resource)
    result = await run_workflow(context, nodes, Deadline(10))
    assert result["resource_type"] == resource["resource_type"]
    assert stages == ["planning", "generating", "validating", "formatting"]
    assert len(checks) == 2 and checks[-1][2]["final"]
    assert "completed" not in stages  # Publication belongs to the backend transaction.
    assert "human_pass" not in result


async def test_invalid_shape_regenerates_at_most_twice_with_feedback():
    context, nodes, stages, checks, calls = build_nodes(RESOURCES[0], bad_candidates=2)
    await run_workflow(context, nodes, Deadline(10))
    assert len(calls) == 3 and calls[1] and calls[2]
    assert [check[1] for check in checks] == [False, False, True, True]
    context, nodes, stages, checks, calls = build_nodes(RESOURCES[0], bad_candidates=3)
    with pytest.raises(ContentRejected):
        await run_workflow(context, nodes, Deadline(10))
    assert len(calls) == 3 and "formatting" not in stages


@pytest.mark.parametrize("mode", ["wrong_source", "corrupt_format", "verifier_crashes"])
async def test_source_scope_final_corruption_and_verifier_exception_fail_closed(mode):
    context, nodes, stages, checks, calls = build_nodes(RESOURCES[0], **{mode: True})
    with pytest.raises((ContentRejected, RuntimeError)):
        await run_workflow(context, nodes, Deadline(10))
    if mode == "wrong_source":
        assert not calls
