from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import current_user, database
from backend.app.core.errors import AppError
from backend.app.db.models import Course, ProfileRevision, User
from backend.app.schemas.business import ProfileConfirmation
from backend.app.schemas.responses import CourseResponse, ProfileResponse

router = APIRouter(prefix="/courses", tags=["courses", "profiles"])


def require_course(db: Session, course_id: str, *, enabled: bool = True) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise AppError(404, "NOT_FOUND", "课程不存在")
    if enabled and not course.enabled:
        raise AppError(409, "COURSE_DISABLED", "课程暂未开放")
    return course


def latest_profile(db: Session, user_id, course_id) -> ProfileRevision | None:
    return db.scalar(
        select(ProfileRevision)
        .where(ProfileRevision.user_id == user_id, ProfileRevision.course_id == course_id)
        .order_by(ProfileRevision.version.desc())
        .limit(1)
    )


def profile_public(profile):
    return (
        {"version": profile.version, "fields": profile.fields}
        if profile
        else {"version": 0, "fields": None}
    )


@router.get("", response_model=list[CourseResponse])
def courses(user: User = Depends(current_user), db: Session = Depends(database)):
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "enabled": c.enabled,
            "knowledge_ready": bool(c.active_index_version),
            "version": c.content_version,
        }
        for c in db.scalars(select(Course).order_by(Course.id))
    ]


@router.get("/{course_id}/chapters")
def chapters(
    course_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(database),
):
    from backend.app.services.chapters import reviewed_chapters

    require_course(db, course_id)
    return [
        {"id": chapter["id"], "title": chapter["title"]}
        for chapter in reviewed_chapters(request.app.state.settings, course_id)
    ]


@router.get("/{course_id}/profile", response_model=ProfileResponse)
def profile(course_id: str, user: User = Depends(current_user), db: Session = Depends(database)):
    require_course(db, course_id, enabled=False)
    return profile_public(latest_profile(db, user.id, course_id))


@router.put("/{course_id}/profile", response_model=ProfileResponse)
def confirm_profile(
    course_id: str,
    payload: ProfileConfirmation,
    user: User = Depends(current_user),
    db: Session = Depends(database),
):
    require_course(db, course_id)
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    previous = latest_profile(db, user.id, course_id)
    version = previous.version if previous else 0
    if payload.expected_version != version:
        raise AppError(409, "VERSION_CONFLICT", "画像已在其他页面更新，请重新确认")
    fields = payload.model_dump(exclude={"expected_version"})
    if previous and fields == previous.fields:
        return profile_public(previous)
    result = ProfileRevision(
        user_id=user.id, course_id=course_id, version=version + 1, fields=fields
    )
    db.add(result)
    db.commit()
    return profile_public(result)
