from collections.abc import Generator
from datetime import UTC, datetime
from secrets import compare_digest

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.core.security import token_digest
from backend.app.db.models import LoginSession, User


def database(request: Request) -> Generator[Session]:
    engine = request.app.state.database_engine
    if engine is None:
        raise AppError(503, "NOT_READY", "数据库尚未配置")
    with Session(engine, expire_on_commit=False) as session:
        yield session


def current_session(request: Request, db: Session = Depends(database)) -> LoginSession:
    token = request.cookies.get("lga_session", "")
    login = (
        db.scalar(
            select(LoginSession).where(
                LoginSession.token_hash == token_digest(token),
                LoginSession.expires_at > datetime.now(UTC),
            )
        )
        if token
        else None
    )
    if login is None:
        raise AppError(401, "AUTH_REQUIRED", "请先登录")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not compare_digest(csrf, login.csrf_token):
            raise AppError(403, "CSRF_FAILED", "请求校验失败，请刷新页面")
        verify_origin(request)
    return login


def current_user(
    db: Session = Depends(database), login: LoginSession = Depends(current_session)
) -> User:
    user = db.get(User, login.user_id)
    if user is None:
        raise AppError(401, "AUTH_REQUIRED", "请先登录")
    return user


def verify_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if origin and origin not in request.app.state.settings.allowed_origins:
        raise AppError(403, "CSRF_FAILED", "请求来源不受信任")
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise AppError(403, "CSRF_FAILED", "请求来源不受信任")
