import json

import httpx
import pytest

from agents.providers.http import HttpModelProvider, SafeTransport, validate_base_url
from agents.schemas.models import (
    ModelErrorCode,
    ModelFailure,
    ModelMessage,
    ModelRequest,
    ModelSelection,
)


async def public_dns(host, port):
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "protocol,path,response",
    [
        (
            "chat_completions",
            "/v1/chat/completions",
            {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]},
        ),
        (
            "responses",
            "/v1/responses",
            {
                "status": "completed",
                "output": [
                    {"type": "reasoning"},
                    {"type": "message", "content": [{"type": "output_text", "text": "ok"}]},
                ],
            },
        ),
        (
            "messages",
            "/v1/messages",
            {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]},
        ),
        (
            "gemini",
            "/v1/models/chosen:generateContent",
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]},
        ),
    ],
)
async def test_protocol_encoding_and_response_without_real_api(protocol, path, response):
    requests = []

    async def handler(request):
        requests.append(request)
        assert request.url.path == path
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "models.example.com"
        assert request.extensions["sni_hostname"] == "models.example.com"
        payload = json.loads(request.content)
        if protocol == "messages":
            assert payload["system"] == "rules" and payload["max_tokens"] > 0
            assert request.headers["x-api-key"] == "test-secret"
        elif protocol == "gemini":
            assert request.headers["x-goog-api-key"] == "test-secret"
        else:
            assert payload["model"] == "chosen"
            assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(200, json=response)

    provider = HttpModelProvider(
        "https://models.example.com/v1",
        "test-secret",
        SafeTransport([], resolver=public_dns, transport=httpx.MockTransport(handler)),
    )
    result = await provider.generate(
        ModelRequest(
            selection=ModelSelection(
                configuration_id="fixture",
                configuration_version=1,
                protocol=protocol,
                model_id="chosen",
            ),
            messages=(
                ModelMessage(role="system", content="rules"),
                ModelMessage(role="user", content="hi"),
            ),
        ),
        timeout_seconds=1,
    )
    assert result.text == "ok" and len(requests) == 1
    assert result.usage.input_tokens is None


@pytest.mark.parametrize(
    "status,code",
    [
        (401, ModelErrorCode.AUTH),
        (403, ModelErrorCode.AUTH),
        (404, ModelErrorCode.NOT_FOUND),
        (429, ModelErrorCode.RATE_LIMIT),
        (500, ModelErrorCode.UNAVAILABLE),
        (503, ModelErrorCode.UNAVAILABLE),
        (302, ModelErrorCode.UNSUPPORTED),
    ],
)
async def test_http_failures_do_not_echo_provider_secrets_or_retry(status, code):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Retry-After": "3", "Location": "http://localhost/"},
            json={"error": "LEAKED-SECRET"},
        )

    transport = SafeTransport([], resolver=public_dns, transport=httpx.MockTransport(handler))
    with pytest.raises(ModelFailure) as error:
        await transport.post("https://example.com/v1", headers={}, payload={}, timeout_seconds=1)
    assert error.value.code == code and "LEAKED-SECRET" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"]
)
async def test_private_dns_is_blocked_before_sending_credentials(address):
    async def resolver(host, port):
        return [address]

    async def handler(request):
        pytest.fail("Credentials must never be sent to unapproved private destinations")

    with pytest.raises(ModelFailure):
        await SafeTransport([], resolver=resolver, transport=httpx.MockTransport(handler)).post(
            "https://example.com/v1",
            headers={"Authorization": "secret"},
            payload={},
            timeout_seconds=1,
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com",
        "https://user:key@example.com",
        "https://example.com?key=secret",
        "https://example.com/#fragment",
    ],
)
def test_unsafe_url_forms_are_rejected(url):
    with pytest.raises(ModelFailure):
        validate_base_url(url, [])


@pytest.mark.parametrize(
    "tag,expected,retry",
    [
        ("insufficient_quota", ModelErrorCode.QUOTA, False),
        ("project_spend_limit_exceeded", ModelErrorCode.QUOTA, False),
        ("rate_limit_exceeded", ModelErrorCode.THROTTLED, True),
        ("unknown", ModelErrorCode.RATE_LIMIT, True),
    ],
)
async def test_429_diagnostics(tag, expected, retry):
    def handler(request):
        return httpx.Response(429, json={"error": {"code": tag, "message": "private"}})

    transport = SafeTransport([], resolver=public_dns, transport=httpx.MockTransport(handler))
    with pytest.raises(ModelFailure) as err:
        await transport.post("https://example.com/v1", headers={}, payload={}, timeout_seconds=1)
    assert err.value.code == expected and err.value.retryable == retry
    assert "private" not in str(err.value)
