"""LangGraph orchestration. Only the backend can publish a validated candidate."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from agents.schemas.resources import ResourceDraft, resource_draft_adapter
from agents.schemas.workflow import ContentVerdict, ResourcePlan, SourceFragment, WorkflowInput
from agents.validators.sources import check_sources
from agents.workflows.runtime import Deadline


class ContentRejected(Exception):
    def __init__(self):
        super().__init__("CONTENT_REJECTED")


@dataclass(frozen=True)
class WorkflowNodes:
    retrieve: Callable[[WorkflowInput], Awaitable[tuple[SourceFragment, ...]]]
    plan: Callable[[WorkflowInput, tuple[SourceFragment, ...]], Awaitable[ResourcePlan]]
    generate: Callable[
        [WorkflowInput, ResourcePlan, tuple[SourceFragment, ...], tuple[str, ...]], Awaitable[dict]
    ]
    verify: Callable[
        [WorkflowInput, ResourceDraft, tuple[SourceFragment, ...]], Awaitable[ContentVerdict]
    ]
    format: Callable[[ResourceDraft], Awaitable[dict]]
    stage: Callable[[str], Awaitable[None]]
    record: Callable[[int, bool, dict], Awaitable[None]]


class GraphState(TypedDict, total=False):
    context: WorkflowInput
    sources: tuple[SourceFragment, ...]
    plan: ResourcePlan
    candidate: dict
    feedback: tuple[str, ...]
    regenerations: int
    passed: bool
    final: dict


def build_graph(nodes: WorkflowNodes, budget: Deadline, *, regeneration_limit: int = 2):
    if not 0 <= regeneration_limit <= 2:
        raise ValueError("Regeneration limit must be between zero and two")

    async def planning(state: GraphState):
        await nodes.stage("planning")
        context = state["context"]
        sources = await budget.run(lambda: nodes.retrieve(context))
        if not sources or any(
            source.course_id != context.course_id
            or source.index_version != context.knowledge_version
            or (source.visibility == "private" and source.owner_id != context.user_id)
            for source in sources
        ):
            raise ContentRejected()
        plan = await budget.run(lambda: nodes.plan(context, sources))
        return {"sources": sources, "plan": plan, "regenerations": 0, "feedback": ()}

    async def generating(state: GraphState):
        await nodes.stage("generating")
        candidate = await budget.run(
            lambda: nodes.generate(
                state["context"], state["plan"], state["sources"], state["feedback"]
            )
        )
        return {"candidate": candidate}

    async def validate(state: GraphState, candidate: dict):
        try:
            resource = resource_draft_adapter.validate_python(candidate)
        except ValidationError:
            return ("输出结构不符合所选资源契约",), {"structure": False}
        if resource.resource_type != state["context"].resource_type:
            return ("输出资源类型与请求不符",), {"resource_type": False}
        issues = check_sources(resource, state["context"], state["sources"])
        if issues:
            return issues, {"sources": False}
        verdict = await budget.run(
            lambda: nodes.verify(state["context"], resource, state["sources"])
        )
        # A verifier exception escapes and fails the task; it can never imply acceptance.
        return (() if verdict.passed else verdict.issues or ("内容核验未通过",)), {
            "structure": True,
            "sources": True,
            **verdict.model_dump(exclude={"issues"}),
        }

    async def validating(state: GraphState):
        await nodes.stage("validating")
        issues, checks = await validate(state, state["candidate"])
        await nodes.record(state["regenerations"], not issues, checks)
        if issues and state["regenerations"] >= regeneration_limit:
            raise ContentRejected()
        return {
            "feedback": issues,
            "passed": not issues,
            "regenerations": state["regenerations"] + (1 if issues else 0),
        }

    async def formatting(state: GraphState):
        await nodes.stage("formatting")
        resource = resource_draft_adapter.validate_python(state["candidate"])
        final = await budget.run(lambda: nodes.format(resource))
        issues, checks = await validate(state, final)
        await nodes.record(state["regenerations"], not issues, {"final": True, **checks})
        if issues:
            raise ContentRejected()
        return {"final": resource_draft_adapter.validate_python(final).model_dump(mode="json")}

    graph = StateGraph(GraphState)
    for name, action in (
        ("planning", planning),
        ("generating", generating),
        ("validating", validating),
        ("formatting", formatting),
    ):
        graph.add_node(name, action)
    graph.add_edge(START, "planning")
    graph.add_edge("planning", "generating")
    graph.add_edge("generating", "validating")
    graph.add_conditional_edges(
        "validating", lambda state: "formatting" if state["passed"] else "generating"
    )
    graph.add_edge("formatting", END)
    return graph.compile()


async def run_workflow(
    context: WorkflowInput, nodes: WorkflowNodes, budget: Deadline, *, regeneration_limit: int = 2
) -> dict:
    graph = build_graph(nodes, budget, regeneration_limit=regeneration_limit)
    result = await budget.run(lambda: graph.ainvoke({"context": context}, {"recursion_limit": 20}))
    return result["final"]
