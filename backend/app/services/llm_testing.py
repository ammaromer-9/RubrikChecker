"""Test doubles for the LLM layer. Tests must never call the real API."""

from __future__ import annotations

from collections.abc import Callable

from app.services.llm_client import CallRecord, LLMResponse, Message

Reply = str | Exception
Handler = Callable[[str, list[Message]], str]


class FakeLLMProvider:
    """Replays scripted replies in order, or answers via a handler function.

    A reply that is an Exception is raised instead of returned.
    """

    def __init__(
        self,
        replies: list[Reply] | None = None,
        *,
        handler: Handler | None = None,
        model: str = "fake-model",
    ) -> None:
        self.model = model
        self._replies = list(replies or [])
        self._handler = handler
        self.calls: list[tuple[str, list[Message]]] = []

    def use_handler(self, handler: Handler) -> None:
        self._handler = handler

    def add_replies(self, *replies: Reply) -> None:
        self._replies.extend(replies)

    async def complete(
        self, *, system: str, messages: list[Message], max_tokens: int, temperature: float
    ) -> LLMResponse:
        self.calls.append((system, messages))
        if self._handler is not None:
            text = self._handler(system, messages)
        else:
            if not self._replies:
                raise AssertionError("FakeLLMProvider ran out of scripted replies")
            reply = self._replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            text = reply
        return LLMResponse(text=text, input_tokens=10, output_tokens=5, model=self.model)


class InMemoryCallRecorder:
    def __init__(self) -> None:
        self.calls: list[CallRecord] = []

    async def record(self, call: CallRecord) -> None:
        self.calls.append(call)
