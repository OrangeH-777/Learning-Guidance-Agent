import hashlib
import re

from sqlalchemy.orm import Session

from agents.providers.http import SafeTransport
from agents.retrieval.embedding import OpenAICompatibleEmbedder
from agents.retrieval.vector import search
from agents.schemas.workflow import WorkflowInput
from agents.workflows.runtime import Deadline, ModelCallRunner
from backend.app.core.config import Settings
from backend.app.core.errors import AppError


def embedder_for(settings: Settings):
    if (
        settings.embedding_protocol != "openai_compatible"
        or not settings.embedding_base_url
        or not settings.embedding_model
        or not settings.embedding_dimensions
        or not settings.embedding_index_version
        or not settings.embedding_api_key.get_secret_value()
    ):
        raise AppError(503, "EMBEDDING_NOT_CONFIGURED", "部署方尚未配置统一嵌入模型")
    return OpenAICompatibleEmbedder(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key.get_secret_value(),
        model_id=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        transport=SafeTransport(
            settings.model_endpoint_allowlist, openai_proxy_port=settings.openai_proxy_port
        ),
    )


async def retrieve_context(
    engine,
    context: WorkflowInput,
    settings: Settings,
    deadline: Deadline,
    embedder_factory=embedder_for,
):
    embedder = embedder_factory(settings)
    if not compatible_index(context.knowledge_version, settings):
        raise AppError(409, "INDEX_VERSION_UNAVAILABLE", "原任务使用的嵌入索引版本当前不可用")
    runner = ModelCallRunner(
        deadline,
        call_timeout_seconds=settings.model_call_timeout_seconds,
        transport_retry_limit=settings.model_transport_retry_limit,
    )
    vectors = await runner.call(
        lambda timeout: embedder.embed([context.topic], timeout_seconds=timeout)
    )
    with Session(engine) as db:
        fragments = search(
            db,
            user_id=context.user_id,
            course_id=context.course_id,
            index_version=context.knowledge_version,
            model_id=embedder.model_id,
            vector=vectors[0],
            dimensions=embedder.dimensions,
            limit=settings.retrieval_top_k,
            max_cosine_distance=settings.retrieval_max_cosine_distance,
        )
    if not fragments:
        raise AppError(409, "NO_KNOWLEDGE", "没有检索到匹配材料，请调整主题或补充课程资料")
    return fragments


def web_index_prefix(settings: Settings) -> str:
    # One configured embedding family, separate immutable revisions for each course.
    digest = hashlib.sha256(settings.embedding_index_version.encode()).hexdigest()[:32]
    return f"web-{digest}-"


def compatible_index(version: str | None, settings: Settings) -> bool:
    if not version or not settings.embedding_index_version:
        return False
    return version == settings.embedding_index_version or bool(
        re.fullmatch(re.escape(web_index_prefix(settings)) + r"[0-9a-f]{32}", version)
    )
