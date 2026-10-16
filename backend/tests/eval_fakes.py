"""A fake LLM for evaluation tests: grades per criterion or holistically, and parses rubrics."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from app.services.llm_client import LLMClient, Message
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder
from tests.grading_script import LABELS, RUBRIC, grade_reply

# Maps criterion id -> points the fake grader will "decide" on.
Points = dict[str, int]


class FakeGrader:
    def __init__(self, points: Points | Callable[[str], Points], quote: str = "", bad_quote: bool = False,
                 omit_evidence: bool = False) -> None:
        self._points = points
        self.quote = quote
        self.bad_quote = bad_quote
        self.omit_evidence = omit_evidence
        self.prompts: list[str] = []

    def points(self, prompt: str) -> Points:
        return self._points(prompt) if callable(self._points) else self._points

    def _evidence(self, prompt: str) -> list[dict]:
        if '"evidence"' not in prompt or self.omit_evidence or not self.quote:
            return []
        text = "This sentence is invented by the model." if self.bad_quote else self.quote
        return [{"quote": text, "supports": "met"}]

    def handler(self, system: str, messages: list[Message]) -> str:
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        if "convert grading rubrics" in system:
            return json.dumps(RUBRIC)
        assert "careful, consistent grader" in system, system
        decided = self.points(prompt)
        if "Grade every criterion in one pass" in prompt:
            ids = re.findall(r"Criterion ID: (\S+)", prompt)
            return json.dumps({"criteria": {
                cid: {"reasoning": "r", "level_label": LABELS[cid][decided[cid]],
                      "evidence": self._evidence(prompt)}
                for cid in ids
            }})
        cid = re.search(r"Criterion ID: (\S+)", prompt).group(1)  # type: ignore[union-attr]
        return grade_reply(cid, decided[cid], self._evidence(prompt))


def make_client_factory(grader: FakeGrader, providers: list[FakeLLMProvider] | None = None):
    """A ClientFactory (model, recorder) -> LLMClient that talks to `grader`."""

    def factory(model: str | None, recorder: InMemoryCallRecorder) -> LLMClient:
        provider = FakeLLMProvider(handler=grader.handler, model=model or "fake-default")
        if providers is not None:
            providers.append(provider)
        return LLMClient(provider, recorder, base_delay=0)

    return factory
