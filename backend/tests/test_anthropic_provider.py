"""AnthropicProvider against a stubbed SDK client (no network).

These guard the exact arguments sent to the SDK: the mocked LLM used elsewhere cannot
catch a call the real SDK would reject (e.g. the removed `temperature` parameter).
"""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx2
import pytest

from app.services.llm_client import AnthropicProvider, LLMConfigError, LLMError, TransientLLMError

MESSAGES = [{"role": "user", "content": "hi"}]


def make_provider(effort: str = "") -> AnthropicProvider:
    return AnthropicProvider(api_key="k", model="claude-sonnet-5-5", timeout=5, effort=effort)


def reply(text: str = "{}", stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        model="claude-sonnet-5-5",
        stop_reason=stop_reason,
    )


def stub(provider: AnthropicProvider, **kwargs) -> AsyncMock:
    mock = AsyncMock(**kwargs)
    provider._client.messages.create = mock  # type: ignore[method-assign]
    return mock


def api_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    response = httpx2.Response(status, request=httpx2.Request("POST", "http://test"))
    return cls("boom", response=response, body=None)


def test_installed_sdk_accepts_every_argument_we_send() -> None:
    accepted = set(inspect.signature(anthropic.AsyncAnthropic().messages.create).parameters)
    assert {"model", "system", "messages", "max_tokens", "output_config"} <= accepted
    assert "temperature" not in accepted  # why the provider interface has none


async def test_sends_only_supported_arguments_and_returns_text_blocks_only() -> None:
    provider = make_provider(effort="medium")
    mock = stub(provider, return_value=reply('{"ok": true}'))
    result = await provider.complete(system="sys", messages=MESSAGES, max_tokens=16000)
    kwargs = mock.await_args.kwargs
    assert kwargs == {
        "model": "claude-sonnet-5-5", "system": "sys", "messages": MESSAGES,
        "max_tokens": 16000, "output_config": {"effort": "medium"},
    }
    assert result.text == '{"ok": true}'  # thinking block ignored
    assert (result.input_tokens, result.output_tokens) == (11, 7)


async def test_effort_is_omitted_when_not_configured() -> None:
    provider = make_provider(effort="")
    mock = stub(provider, return_value=reply())
    await provider.complete(system="s", messages=MESSAGES, max_tokens=100)
    assert "output_config" not in mock.await_args.kwargs


async def test_refusal_is_an_error_not_empty_output() -> None:
    provider = make_provider()
    stub(provider, return_value=reply("", stop_reason="refusal"))
    with pytest.raises(LLMError, match="declined"):
        await provider.complete(system="s", messages=MESSAGES, max_tokens=100)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (api_error(anthropic.AuthenticationError, 401), LLMConfigError),
        (api_error(anthropic.PermissionDeniedError, 403), LLMConfigError),
        (api_error(anthropic.RateLimitError, 429), TransientLLMError),
        (api_error(anthropic.InternalServerError, 500), TransientLLMError),
        (api_error(anthropic.BadRequestError, 400), LLMError),
    ],
)
async def test_sdk_errors_map_to_our_error_types(error: Exception, expected: type[LLMError]) -> None:
    provider = make_provider()
    stub(provider, side_effect=error)
    with pytest.raises(expected) as caught:
        await provider.complete(system="s", messages=MESSAGES, max_tokens=100)
    # Only rate limits / 5xx may be retried.
    assert isinstance(caught.value, TransientLLMError) == (expected is TransientLLMError)


async def test_connection_errors_are_transient() -> None:
    provider = make_provider()
    stub(provider, side_effect=anthropic.APIConnectionError(request=httpx2.Request("POST", "http://t")))
    with pytest.raises(TransientLLMError):
        await provider.complete(system="s", messages=MESSAGES, max_tokens=100)
