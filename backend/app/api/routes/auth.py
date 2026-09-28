from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import current_session, current_user, database, verify_origin
from backend.app.core.errors import AppError
from backend.app.core.security import hash_password, new_token, token_digest, verify_password
from backend.app.db.models import LoginSession, User
from backend.app.schemas.inputs import InputModel, RegistrationInput, Username
from backend.app.schemas.responses import SessionResponse

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(InputModel):
    username: Username
    password: SecretStr = Field(repr=False)


def start_session(request: Request, response: Response, db: Session, user: User) -> dict:
    # Replace an existing browser session to prevent stale sessions after switching accounts.
    previous = request.cookies.get("lga_session")
    if previous:
        existing = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == token_digest(previous))
        )
        if existing:
            db.delete(existing)
    token, csrf = new_token(), new_token()
    ttl = request.app.state.settings.session_ttl_seconds
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=token_digest(token),
            csrf_token=csrf,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
        )
    )
    db.commit()
    response.set_cookie(
        "lga_session",
        token,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        max_age=ttl,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": {"id": str(user.id), "username": user.username}, "csrf_token": csrf}


@router.post("/register", status_code=201, response_model=SessionResponse)
def register(
    payload: RegistrationInput,
    request: Request,
    response: Response,
    db: Session = Depends(database),
):
    verify_origin(request)
    user = User(
        username=payload.username, password_hash=hash_password(payload.password.get_secret_value())
    )
    db.add(user)
    try:
        db.flush()
        return start_session(request, response, db, user)
    except IntegrityError:
        db.rollback()
        raise AppError(409, "USERNAME_TAKEN", "该账号已被使用") from None


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginInput, request: Request, response: Response, db: Session = Depends(database)
):
    verify_origin(request)
    user = db.scalar(select(User).where(User.username == payload.username.lower()))
    if not verify_password(
        user.password_hash if user else None, payload.password.get_secret_value()
    ):
        raise AppError(401, "AUTH_FAILED", "账号或密码错误")
    return start_session(request, response, db, user)


@router.get("/session", response_model=SessionResponse)
def session(
    response: Response,
    user: User = Depends(current_user),
    login: LoginSession = Depends(current_session),
):
    response.headers["Cache-Control"] = "no-store"
    return {"user": {"id": str(user.id), "username": user.username}, "csrf_token": login.csrf_token}


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    login: LoginSession = Depends(current_session),
    db: Session = Depends(database),
):
    db.delete(login)
    db.commit()
    response.delete_cookie("lga_session", path="/")
