from agents.providers.http import SafeTransport
from agents.retrieval.vector import validate_vector
from agents.schemas.models import ModelErrorCode, ModelFailure


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        dimensions: int,
        transport: SafeTransport,
    ):
        self.base_url, self._api_key = base_url.rstrip("/"), api_key
        self.model_id, self.dimensions, self.transport = model_id, dimensions, transport

    async def embed(self, texts: list[str], *, timeout_seconds: float) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("Embedding input must not be empty")
        data = await self.transport.post(
            self.base_url + "/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            payload={"model": self.model_id, "input": texts, "encoding_format": "float"},
            timeout_seconds=timeout_seconds,
        )
        try:
            rows = data["data"]
            if len(rows) != len(texts) or sorted(row["index"] for row in rows) != list(
                range(len(texts))
            ):
                raise ValueError()
            return [
                validate_vector(row["embedding"], self.dimensions)
                for row in sorted(rows, key=lambda row: row["index"])
            ]
        except (KeyError, TypeError, ValueError):
            raise ModelFailure(ModelErrorCode.FORMAT) from None
