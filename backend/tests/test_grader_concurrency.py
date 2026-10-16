import asyncio

from app.schemas.rubric import Rubric
from app.services.grader import grade_all_criteria
from app.services.llm_client import LLMClient, LLMResponse
from app.services.llm_testing import InMemoryCallRecorder
from tests.grading_script import DRAFT, RUBRIC, grade_reply


class TrackingProvider:
    model = "tracking"

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0
        self.total = 0

    async def complete(self, *, system, messages, max_tokens, temperature) -> LLMResponse:
        self.in_flight += 1
        self.total += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0.01)  # a real suspension point, so calls can overlap
        self.in_flight -= 1
        criterion_id = "thesis" if "Criterion ID: thesis" in messages[0]["content"] else "support"
        points = 10 if criterion_id == "thesis" else 6
        return LLMResponse(grade_reply(criterion_id, points), 1, 1, self.model)


async def run(concurrency: int) -> TrackingProvider:
    provider = TrackingProvider()
    llm = LLMClient(provider, InMemoryCallRecorder())
    runs = await grade_all_criteria(
        llm, Rubric.model_validate(RUBRIC), instructions="x", draft=DRAFT,
        num_runs=3, temperature=0.7, concurrency=concurrency, grading_id=None,
    )
    assert {k: len(v) for k, v in runs.items()} == {"thesis": 3, "support": 3}
    return provider


async def test_concurrency_is_limited() -> None:
    provider = await run(concurrency=2)
    assert provider.total == 6 and provider.peak == 2


async def test_calls_actually_run_concurrently_when_allowed() -> None:
    provider = await run(concurrency=6)
    assert provider.peak > 2
