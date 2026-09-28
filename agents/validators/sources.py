from agents.schemas.resources import ResourceDraft
from agents.schemas.workflow import SourceFragment, WorkflowInput


def check_sources(
    resource: ResourceDraft, context: WorkflowInput, fragments: tuple[SourceFragment, ...]
) -> tuple[str, ...]:
    allowed = {
        str(fragment.id)
        for fragment in fragments
        if fragment.course_id == context.course_id
        and fragment.index_version == context.knowledge_version
        and (fragment.visibility == "public" or fragment.owner_id == context.user_id)
    }
    if not resource.source_ids or any(source not in allowed for source in resource.source_ids):
        return ("来源缺失、不属于检索材料或没有访问权限",)
    return ()
