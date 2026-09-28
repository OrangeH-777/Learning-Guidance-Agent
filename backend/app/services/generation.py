import time
from uuid import UUID

from sqlalchemy.orm import Session

from agents.nodes.model_nodes import LearningModelNodes
from agents.prompts.version import PROMPT_VERSION
from agents.schemas.workflow import ProfileSnapshot, WorkflowInput
from agents.workflows.learning import ContentRejected, WorkflowNodes, run_workflow
from agents.workflows.runtime import Deadline, ModelCallRunner
from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask, ModelConfiguration, ValidationRecord
from backend.app.services.knowledge import retrieve_context
from backend.app.services.models import selection_for
from backend.app.services.tasks import advance_task, publish_resource
from backend.app.tasks.state import TaskStatus


async def generate_resource(app, task_id: UUID, budget: Deadline):
    settings, engine = app.state.settings, app.state.database_engine
    with Session(engine) as db:
        task = db.get(GenerationTask, task_id)
        if task.prompt_version != PROMPT_VERSION:
            raise AppError(
                409, "PROMPT_VERSION_UNAVAILABLE", "原任务的提示词版本当前不可用，请创建新任务"
            )
        config = db.get(ModelConfiguration, task.model_configuration_id)
        if config.user_id != task.user_id:
            raise AppError(404, "NOT_FOUND", "模型配置不存在")
        context = WorkflowInput(
            task_id=task.id,
            user_id=task.user_id,
            course_id=task.course_id,
            topic=task.topic,
            resource_type=task.resource_type,
            profile=ProfileSnapshot(version=task.profile_version, **task.profile_snapshot),
            model=selection_for(config),
            knowledge_version=task.knowledge_version,
            prompt_version=task.prompt_version,
        )
        provider = app.state.provider_factory(config, settings)
    runner = ModelCallRunner(
        budget,
        call_timeout_seconds=settings.model_call_timeout_seconds,
        transport_retry_limit=settings.model_transport_retry_limit,
    )
    model_nodes = LearningModelNodes(provider, runner, context)
    spans = []
    active_node = None
    node_started = time.monotonic()

    def finish_node():
        nonlocal node_started
        now = time.monotonic()
        if active_node is not None:
            spans.append({"node": active_node, "elapsed_seconds": round(now - node_started, 6)})
        node_started = now

    async def retrieve(ctx):
        return await retrieve_context(engine, ctx, settings, budget, app.state.embedder_factory)

    async def stage(value):
        nonlocal active_node
        finish_node()
        active_node = value
        budget.remaining()
        with Session(engine) as db, db.begin():
            advance_task(
                db,
                task_id,
                TaskStatus(value),
                regeneration_limit=settings.content_regeneration_limit,
            )

    async def record(attempt, passed, checks):
        budget.remaining()
        with Session(engine) as db, db.begin():
            db.add(ValidationRecord(task_id=task_id, attempt=attempt, passed=passed, checks=checks))

    nodes = WorkflowNodes(
        retrieve,
        model_nodes.plan,
        model_nodes.generate,
        model_nodes.verify,
        model_nodes.format,
        stage,
        record,
    )
    try:
        final = await run_workflow(
            context, nodes, budget, regeneration_limit=settings.content_regeneration_limit
        )
    except ContentRejected:
        raise AppError(422, "CONTENT_REJECTED", "内容未通过核验") from None
    finally:
        finish_node()
        from sqlalchemy.exc import SQLAlchemyError

        try:
            with Session(engine) as db, db.begin():
                observed = db.get(GenerationTask, task_id)
                observed.telemetry = {
                    "task_id": str(task_id),
                    "protocol": context.model.protocol.value,
                    "model_id": context.model.model_id,
                    "knowledge_version": context.knowledge_version,
                    "prompt_version": context.prompt_version,
                    "nodes": spans,
                    "model_attempts": runner.attempts,
                    "transport_retries": runner.transport_retries,
                    "usage": model_nodes.usage,
                }
        except SQLAlchemyError:
            # Do not mask the original failure when telemetry storage is unavailable.
            pass
    metadata = {
        "profile": context.profile.model_dump(),
        "model": context.model.model_dump(mode="json"),
        "knowledge_version": context.knowledge_version,
        "prompt_version": context.prompt_version,
        "ai_notice": "由AI生成，仅供参考",
        "automatic_checks": "passed",
        "human_pass": False,
    }
    budget.remaining()
    with Session(engine) as db, db.begin():
        publish_resource(db, task_id, final, metadata)
