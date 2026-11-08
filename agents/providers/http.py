"""Pinned-address HTTP transport and four text-only protocol adapters."""

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from agents.schemas.models import (
    ModelErrorCode,
    ModelFailure,
    ModelProtocol,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from agents.workflows.runtime import parse_retry_after


def validate_base_url(value: str, allowlist: list[str]) -> httpx.URL:
    try:
        url = httpx.URL(value)
        if not url.host or url.username or url.password or url.query or url.fragment:
            raise ValueError()
        if url.scheme not in {"https", "http"}:
            raise ValueError()
        origin = str(url.copy_with(path="/", query=None, fragment=None)).rstrip("/")
        if url.scheme != "https" and origin not in allowlist:
            raise ValueError()
        if any(part in {".", ".."} for part in url.path.split("/")):
            raise ValueError()
        return url
    except (ValueError, httpx.InvalidURL):
        raise ModelFailure(ModelErrorCode.UNSUPPORTED) from None


async def resolve_addresses(host: str, port: int) -> list[str]:
    results = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(item[4][0] for item in results))


async def classify_429(response: httpx.Response) -> ModelErrorCode:
    # Inspect only machine identifiers; never expose or log the provider message.
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > 16384:
            return ModelErrorCode.RATE_LIMIT
        body.extend(chunk)
    try:
        error = json.loads(body)["error"]
        tags = {error.get(k) for k in ("code", "type") if isinstance(error.get(k), str)}
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return ModelErrorCode.RATE_LIMIT
    if tags & {
        "insufficient_quota",
        "credit_balance_exhausted",
        "project_spend_limit_exceeded",
        "organization_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }:
        return ModelErrorCode.QUOTA
    if "rate_limit_exceeded" in tags:
        return ModelErrorCode.THROTTLED
    return ModelErrorCode.RATE_LIMIT


class SafeTransport:
    def __init__(
        self,
        allowlist: list[str],
        *,
        openai_proxy_port: int | None = None,
        resolver: Callable[[str, int], Awaitable[list[str]]] = resolve_addresses,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.allowlist = allowlist
        self.openai_proxy_port = openai_proxy_port
        self.resolver = resolver
        self.transport = transport

    async def post(
        self, url: str, *, headers: dict[str, str], payload: dict, timeout_seconds: float
    ) -> dict:
        parsed = validate_base_url(url, self.allowlist)
        origin = str(parsed.copy_with(path="/", query=None, fragment=None)).rstrip("/")
        try:
            async with asyncio.timeout(timeout_seconds):
                proxy = None
                if self.openai_proxy_port and origin == "https://api.openai.com":
                    proxy = f"http://127.0.0.1:{self.openai_proxy_port}"
                    target = parsed  # CONNECT to the fixed official host; TLS still verifies it.
                else:
                    addresses = await self.resolver(parsed.host, parsed.port or 443)
                    if not addresses:
                        raise ModelFailure(ModelErrorCode.TRANSPORT)
                    if origin not in self.allowlist and any(
                        not ipaddress.ip_address(address).is_global for address in addresses
                    ):
                        raise ModelFailure(ModelErrorCode.UNSUPPORTED)
                    # Pin the approved DNS answer. TLS verification still uses the original hostname.
                    target = parsed.copy_with(host=addresses[0])
                async with httpx.AsyncClient(
                    transport=self.transport,
                    proxy=proxy,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=timeout_seconds,
                ) as client:
                    request = client.build_request(
                        "POST",
                        target,
                        headers={**headers, "Host": parsed.netloc.decode()},
                        json=payload,
                    )
                    request.extensions["sni_hostname"] = parsed.host
                    response = await client.send(request, stream=True)
                    try:
                        if response.status_code in (401, 403):
                            raise ModelFailure(ModelErrorCode.AUTH)
                        if response.status_code == 404:
                            raise ModelFailure(ModelErrorCode.NOT_FOUND)
                        if response.status_code == 429:
                            raise ModelFailure(
                                await classify_429(response),
                                retry_after_seconds=parse_retry_after(
                                    response.headers.get("Retry-After")
                                ),
                            )
                        if response.status_code >= 500:
                            raise ModelFailure(ModelErrorCode.UNAVAILABLE)
                        if response.status_code != 200:
                            raise ModelFailure(ModelErrorCode.UNSUPPORTED)
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 2 * 1024 * 1024:
                                raise ModelFailure(ModelErrorCode.FORMAT)
                        result = json.loads(data)
                        if not isinstance(result, dict):
                            raise ModelFailure(ModelErrorCode.FORMAT)
                        return result
                    finally:
                        await response.aclose()
        except (httpx.TimeoutException, TimeoutError):
            raise ModelFailure(ModelErrorCode.TIMEOUT) from None
        except (httpx.HTTPError, OSError):
            raise ModelFailure(ModelErrorCode.TRANSPORT) from None
        except (ValueError, TypeError):
            raise ModelFailure(ModelErrorCode.FORMAT) from None


class HttpModelProvider:
    def __init__(self, base_url: str, api_key: str, transport: SafeTransport):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.transport = transport

    async def generate(self, request: ModelRequest, *, timeout_seconds: float) -> ModelResponse:
        protocol = request.selection.protocol
        model = request.selection.model_id
        messages = [message.model_dump() for message in request.messages]
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if protocol == ModelProtocol.CHAT_COMPLETIONS:
            endpoint = "/chat/completions"
            payload = {"model": model, "messages": messages, "stream": False}
        elif protocol == ModelProtocol.RESPONSES:
            endpoint = "/responses"
            payload = {"model": model, "input": messages, "stream": False, "store": False}
        elif protocol == ModelProtocol.MESSAGES:
            endpoint = "/messages"
            headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
            payload = {
                "model": model,
                "max_tokens": 4096,
                "system": "\n\n".join(m["content"] for m in messages if m["role"] == "system"),
                "messages": [m for m in messages if m["role"] != "system"],
            }
        else:
            endpoint = f"/models/{quote(model.removeprefix('models/'), safe='')}:generateContent"
            headers = {"x-goog-api-key": self._api_key}
            payload = {
                "systemInstruction": {
                    "parts": [{"text": m["content"]} for m in messages if m["role"] == "system"]
                },
                "contents": [
                    {
                        "role": "model" if m["role"] == "assistant" else "user",
                        "parts": [{"text": m["content"]}],
                    }
                    for m in messages
                    if m["role"] != "system"
                ],
            }
        data = await self.transport.post(
            self.base_url + endpoint,
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        try:
            if protocol == ModelProtocol.CHAT_COMPLETIONS:
                choice = data["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                    raise ValueError()
                text = choice["message"]["content"]
                usage = data.get("usage") or {}
                inputs, outputs = usage.get("prompt_tokens"), usage.get("completion_tokens")
            elif protocol == ModelProtocol.RESPONSES:
                if data.get("status") != "completed":
                    raise ValueError()
                parts = [
                    part
                    for item in data["output"]
                    if item.get("type") == "message"
                    for part in item["content"]
                ]
                if any(part.get("type") == "refusal" for part in parts):
                    raise ValueError()
                text = "\n".join(
                    part["text"] for part in parts if part.get("type") == "output_text"
                )
                usage = data.get("usage") or {}
                inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
            elif protocol == ModelProtocol.MESSAGES:
                if data.get("stop_reason") != "end_turn":
                    raise ValueError()
                text = "\n".join(
                    part["text"] for part in data["content"] if part.get("type") == "text"
                )
                usage = data.get("usage") or {}
                inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
            else:
                candidate = data["candidates"][0]
                if candidate.get("finishReason") != "STOP":
                    raise ValueError()
                text = "\n".join(
                    part["text"]
                    for part in candidate["content"]["parts"]
                    if "text" in part and not part.get("thought")
                )
                usage = data.get("usageMetadata") or {}
                inputs, outputs = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
            if not isinstance(text, str) or not text.strip():
                raise ValueError()
            return ModelResponse(
                text=text,
                model_id=data.get("model", model),
                usage=ModelUsage(input_tokens=inputs, output_tokens=outputs),
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ValidationError):
            raise ModelFailure(ModelErrorCode.FORMAT) from None
