import pytest
from pydantic import BaseModel

from app.services.llm_client import (
    LLMClient,
    LLMError,
    LLMOutputError,
    TransientLLMError,
    extract_json_text,
)
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder


class Answer(BaseModel):
    value: int


def make_client(replies: list, max_retries: int = 2):
    provider = FakeLLMProvider(replies)
    recorder = InMemoryCallRecorder()
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    client = LLMClient(provider, recorder, max_retries=max_retries, base_delay=1.0, sleep=fake_sleep)
    return client, provider, recorder, delays


async def generate(client: LLMClient) -> Answer:
    return await client.generate_structured(
        Answer, purpose="test", system="sys", prompt="give me a value", prompt_version="test.v1"
    )


@pytest.mark.parametrize(
    "text",
    ['{"value": 3}', '```json\n{"value": 3}\n```', 'Sure! Here you go:\n{"value": 3}\nHope that helps.'],
)
def test_extract_json_text_handles_fences_and_prose(text: str) -> None:
    assert Answer.model_validate_json(extract_json_text(text)).value == 3


async def test_parses_valid_json_and_records_call() -> None:
    client, _, recorder, _ = make_client(['{"value": 7}'])
    result = await generate(client)
    assert result.value == 7
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call.success and call.purpose == "test" and call.prompt_version == "test.v1"
    assert call.input_tokens == 10 and call.output_tokens == 5


async def test_invalid_output_is_retried_once_with_the_validation_error() -> None:
    client, provider, recorder, _ = make_client(['{"value": "oops"}', '{"value": 2}'])
    result = await generate(client)
    assert result.value == 2
    retry_messages = provider.calls[1][1]
    assert [m["role"] for m in retry_messages] == ["user", "assistant", "user"]
    assert "value" in retry_messages[2]["content"]  # the validation error is included
    assert [c.success for c in recorder.calls] == [False, True]


async def test_second_invalid_output_raises_clear_error() -> None:
    client, provider, _, _ = make_client(["not json", "still not json"])
    with pytest.raises(LLMOutputError):
        await generate(client)
    assert len(provider.calls) == 2  # exactly one retry


async def test_transient_errors_back_off_exponentially_then_succeed() -> None:
    client, _, recorder, delays = make_client(
        [TransientLLMError("429"), TransientLLMError("503"), '{"value": 1}']
    )
    assert (await generate(client)).value == 1
    assert 1.0 <= delays[0] < 1.5 and 2.0 <= delays[1] < 2.5
    assert [c.success for c in recorder.calls] == [False, False, True]


async def test_gives_up_after_max_retries() -> None:
    client, provider, _, _ = make_client([TransientLLMError("x")] * 3, max_retries=2)
    with pytest.raises(TransientLLMError):
        await generate(client)
    assert len(provider.calls) == 3


async def test_non_transient_errors_are_not_retried() -> None:
    client, provider, recorder, delays = make_client([LLMError("400 bad request")])
    with pytest.raises(LLMError):
        await generate(client)
    assert len(provider.calls) == 1 and delays == []
    assert recorder.calls[0].success is False


async def test_recorder_failure_does_not_break_the_call() -> None:
    class BrokenRecorder:
        async def record(self, call) -> None:
            raise RuntimeError("db down")

    client = LLMClient(FakeLLMProvider(['{"value": 1}']), BrokenRecorder())
    assert (await generate(client)).value == 1
