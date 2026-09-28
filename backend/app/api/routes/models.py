from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.providers.http import validate_base_url
from agents.schemas.models import ModelFailure, ModelMessage, ModelRequest
from backend.app.api.dependencies import current_user, database
from backend.app.core.errors import AppError
from backend.app.db.models import ModelConfiguration, User
from backend.app.schemas.business import ModelConfigurationInput
from backend.app.schemas.responses import (
    MissingModelResponse,
    ModelHistoryResponse,
    ModelTestResponse,
    SavedModelResponse,
)
from backend.app.services.models import (
    call_model_once,
    cipher,
    latest_model,
    model_public,
    selection_for,
)

router = APIRouter(prefix="/model-settings", tags=["model-settings"])


@router.get("", response_model=MissingModelResponse | SavedModelResponse)
def get_model(user: User = Depends(current_user), db: Session = Depends(database)):
    return model_public(latest_model(db, user.id))


@router.get("/history", response_model=ModelHistoryResponse)
def model_history(
    user: User = Depends(current_user),
    db: Session = Depends(database),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
):
    owned = ModelConfiguration.user_id == user.id
    total = db.scalar(select(func.count()).select_from(ModelConfiguration).where(owned))
    records = db.scalars(
        select(ModelConfiguration)
        .where(owned)
        .order_by(ModelConfiguration.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [{**model_public(record), "created_at": record.created_at} for record in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("", response_model=SavedModelResponse)
def save_model(
    payload: ModelConfigurationInput,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(database),
):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    previous = latest_model(db, user.id)
    version = previous.version if previous else 0
    if payload.expected_version != version:
        raise AppError(409, "VERSION_CONFLICT", "模型设置已变化，请刷新后重试")
    validate_base_url(payload.base_url, request.app.state.settings.model_endpoint_allowlist)
    if payload.api_key is not None:
        raw = payload.api_key.get_secret_value()
        if not raw.strip() or len(raw) > 8192:
            raise AppError(422, "INVALID_INPUT", "API Key 不能为空或超过长度限制")
        encoded = cipher(request.app.state.settings).encrypt(raw)
    elif previous and not previous.retired:
        encoded = previous.encrypted_key
    else:
        raise AppError(422, "INVALID_INPUT", "首次设置必须填写 API Key")
    config = ModelConfiguration(
        user_id=user.id,
        version=version + 1,
        protocol=payload.protocol,
        base_url=payload.base_url.rstrip("/"),
        model_id=payload.model_id,
        encrypted_key=encoded,
    )
    db.add(config)
    db.commit()
    return model_public(config)


@router.delete("", status_code=204)
def delete_model(user: User = Depends(current_user), db: Session = Depends(database)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    previous = latest_model(db, user.id)
    if previous and not previous.retired:
        db.add(
            ModelConfiguration(
                user_id=user.id,
                version=previous.version + 1,
                protocol=previous.protocol,
                base_url=previous.base_url,
                model_id=previous.model_id,
                encrypted_key="",
                retired=True,
            )
        )
        db.commit()


@router.post("/test", response_model=ModelTestResponse)
async def test_model(
    request: Request, user: User = Depends(current_user), db: Session = Depends(database)
):
    config = latest_model(db, user.id)
    if not config or config.retired:
        raise AppError(409, "MODEL_NOT_CONFIGURED", "请先保存模型设置")
    provider = request.app.state.provider_factory(config, request.app.state.settings)
    selection = selection_for(config)
    config_id = config.id
    # End the request transaction before external I/O.
    db.commit()
    try:
        await call_model_once(
            provider,
            ModelRequest(
                selection=selection,
                messages=(ModelMessage(role="user", content="请仅回复 OK，用于连接测试。"),),
            ),
            request.app.state.settings.model_call_timeout_seconds,
        )
    except ModelFailure:
        db.get(ModelConfiguration, config_id).tested_at = None
        db.commit()
        raise
    persisted = db.get(ModelConfiguration, config_id)
    persisted.tested_at = datetime.now(UTC)
    db.commit()
    return {"status": "ok", "version": persisted.version}
