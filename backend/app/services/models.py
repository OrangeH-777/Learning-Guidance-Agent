from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.providers.http import HttpModelProvider, SafeTransport
from agents.schemas.models import ModelErrorCode, ModelFailure, ModelSelection
from agents.workflows.runtime import Deadline, ModelCallRunner, TaskDeadlineExceeded
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.core.security import CredentialCipher
from backend.app.db.models import ModelConfiguration


def latest_model(db: Session, user_id) -> ModelConfiguration | None:
    return db.scalar(
        select(ModelConfiguration)
        .where(ModelConfiguration.user_id == user_id)
        .order_by(ModelConfiguration.version.desc())
        .limit(1)
    )


def cipher(settings: Settings) -> CredentialCipher:
    key = settings.model_credential_encryption_key.get_secret_value()
    try:
        return CredentialCipher(([key] if key else []) + settings.model_credential_previous_keys)
    except ValueError:
        raise AppError(503, "ENCRYPTION_NOT_READY", "服务端尚未配置有效的凭据加密密钥") from None


def provider_for(configuration: ModelConfiguration, settings: Settings):
    try:
        key = cipher(settings).decrypt(configuration.encrypted_key)
    except ValueError:
        raise AppError(503, "ENCRYPTION_NOT_READY", "模型凭据暂时不可用") from None
    return HttpModelProvider(
        configuration.base_url,
        key,
        SafeTransport(
            settings.model_endpoint_allowlist, openai_proxy_port=settings.openai_proxy_port
        ),
    )


def selection_for(configuration: ModelConfiguration) -> ModelSelection:
    return ModelSelection(
        configuration_id=str(configuration.id),
        configuration_version=configuration.version,
        protocol=configuration.protocol,
        model_id=configuration.model_id,
    )


async def call_model_once(provider, request, timeout_seconds):
    """One absolute budget for interactive calls; per-read HTTP timeouts are insufficient."""
    runner = ModelCallRunner(
        Deadline(timeout_seconds), call_timeout_seconds=timeout_seconds, transport_retry_limit=0
    )
    try:
        return await runner.call(
            lambda remaining: provider.generate(request, timeout_seconds=remaining)
        )
    except TaskDeadlineExceeded:
        raise ModelFailure(ModelErrorCode.TIMEOUT) from None


def model_public(configuration: ModelConfiguration | None) -> dict:
    if configuration is None:
        return {"version": 0, "configured": False}
    return {
        "version": configuration.version,
        "configured": not configuration.retired,
        "protocol": configuration.protocol,
        "base_url": configuration.base_url,
        "model_id": configuration.model_id,
        "has_key": bool(configuration.encrypted_key),
        "tested_at": configuration.tested_at,
    }
