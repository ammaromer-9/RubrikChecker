"""LLM access: a small provider interface plus a client that adds retries,
structured (Pydantic) output parsing, and per-call logging.

Only `AnthropicProvider` talks to the network. Everything else works against the
`LLMProvider` protocol, so tests inject a fake and another vendor can be added
by implementing one method.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypedDict, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models import LLMCall

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Any failure while calling the LLM."""


class LLMConfigError(LLMError):
    """The LLM is not configured (missing API key or model)."""


class TransientLLMError(LLMError):
    """Rate limit, timeout, connection problem or 5xx. Safe to retry."""


class LLMOutputError(LLMError):
    """The model answered, but not with valid JSON for the requested schema."""


class Message(TypedDict):
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    model: str

    async def complete(
        self, *, system: str, messages: list[Message], max_tokens: int, temperature: float
    ) -> LLMResponse:
        """Return the model's text reply. Raise TransientLLMError for retryable failures."""
        ...


@dataclass(frozen=True)
class CallRecord:
    purpose: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    success: bool
    error: str | None = None
    grading_id: int | None = None


class CallRecorder(Protocol):
    async def record(self, call: CallRecord) -> None: ...


class DbCallRecorder:
    """Writes each call to the `llm_calls` table using its own short-lived session."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, call: CallRecord) -> None:
        async with self._session_factory() as session:
            session.add(
                LLMCall(
                    grading_id=call.grading_id,
                    purpose=call.purpose,
                    model=call.model,
                    prompt_version=call.prompt_version,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    latency_ms=call.latency_ms,
                    success=call.success,
                    error=call.error,
                )
            )
            await session.commit()


class AnthropicProvider:
    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self.model = model
        # SDK retries are disabled: LLMClient owns the retry policy.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=0)

    async def complete(
        self, *, system: str, messages: list[Message], max_tokens: int, temperature: float
    ) -> LLMResponse:
        try:
            response = await self._client.messages.create(
                model=self.model,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            # APITimeoutError is a subclass of APIConnectionError.
            raise TransientLLMError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientLLMError(str(exc)) from exc
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def extract_json_text(text: str) -> str:
    """Pull the JSON object out of a reply that may include code fences or prose."""
    candidate = _FENCE_RE.sub("", text.strip()).strip()
    if candidate.startswith("{") and candidate.endswith("}"):
        return candidate
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        return candidate[start : end + 1]
    return candidate


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        recorder: CallRecorder,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self._recorder = recorder
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._sleep = sleep

    @property
    def model(self) -> str:
        return self.provider.model

    async def generate_structured(
        self,
        schema: type[T],
        *,
        purpose: str,
        system: str,
        prompt: str,
        prompt_version: str,
        grading_id: int | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> T:
        """Call the model and parse its reply into `schema`.

        If the reply fails validation, retry once with the validation error appended
        to the conversation. A second failure raises LLMOutputError.
        """
        messages: list[Message] = [{"role": "user", "content": prompt}]
        last_error = ""
        for _ in range(2):
            started = time.monotonic()
            response = await self._complete_with_retries(
                purpose=purpose,
                prompt_version=prompt_version,
                grading_id=grading_id,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            try:
                parsed = schema.model_validate_json(extract_json_text(response.text))
            except ValidationError as exc:
                last_error = str(exc)[:2000]
                await self._record(
                    response, purpose, prompt_version, grading_id, latency_ms,
                    success=False, error=f"invalid output: {last_error[:500]}",
                )
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": response.text},
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply did not match the required JSON schema:\n"
                            f"{last_error}\n"
                            "Reply again with only the corrected JSON object."
                        ),
                    },
                ]
                continue
            await self._record(response, purpose, prompt_version, grading_id, latency_ms, True)
            return parsed
        raise LLMOutputError(f"Model returned invalid output for {purpose}: {last_error}")

    async def _complete_with_retries(
        self,
        *,
        purpose: str,
        prompt_version: str,
        grading_id: int | None,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        for attempt in range(self._max_retries + 1):
            started = time.monotonic()
            try:
                return await self.provider.complete(
                    system=system, messages=messages, max_tokens=max_tokens, temperature=temperature
                )
            except LLMError as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                await self._safe_record(
                    CallRecord(
                        purpose=purpose, model=self.provider.model, prompt_version=prompt_version,
                        input_tokens=0, output_tokens=0, latency_ms=latency_ms,
                        success=False, error=str(exc)[:500], grading_id=grading_id,
                    )
                )
                if not isinstance(exc, TransientLLMError) or attempt == self._max_retries:
                    raise
                delay = self._base_delay * (2**attempt) + random.uniform(0, self._base_delay / 4)
                logger.warning("LLM call failed (%s); retrying in %.1fs", exc, delay)
                await self._sleep(delay)
        raise AssertionError("unreachable")

    async def _record(
        self,
        response: LLMResponse,
        purpose: str,
        prompt_version: str,
        grading_id: int | None,
        latency_ms: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        await self._safe_record(
            CallRecord(
                purpose=purpose, model=response.model, prompt_version=prompt_version,
                input_tokens=response.input_tokens, output_tokens=response.output_tokens,
                latency_ms=latency_ms, success=success, error=error, grading_id=grading_id,
            )
        )

    async def _safe_record(self, call: CallRecord) -> None:
        # Bookkeeping must never break grading.
        try:
            await self._recorder.record(call)
        except Exception:
            logger.exception("Failed to record LLM call")


def build_llm_client(settings: Settings, recorder: CallRecorder) -> LLMClient:
    if not settings.anthropic_api_key or not settings.anthropic_model:
        raise LLMConfigError("ANTHROPIC_API_KEY and ANTHROPIC_MODEL must be set in .env")
    provider = AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        timeout=settings.llm_timeout_seconds,
    )
    return LLMClient(provider, recorder, max_retries=settings.llm_max_retries)
