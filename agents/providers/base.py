"""Every adapter makes exactly one attempt; the shared runtime owns retries."""

from typing import Protocol

from agents.schemas.models import ModelRequest, ModelResponse


class ModelProvider(Protocol):
    async def generate(self, request: ModelRequest, *, timeout_seconds: float) -> ModelResponse:
        """Call only request.selection; never discover, switch or retry a model implicitly."""
        ...
