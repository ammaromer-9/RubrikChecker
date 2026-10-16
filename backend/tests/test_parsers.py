import json

import pytest

from app.services.llm_client import LLMClient, LLMOutputError
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder
from app.services.requirements_extractor import extract_requirements
from app.services.rubric_parser import parse_rubric

RUBRIC = {
    "criteria": [
        {
            "id": "thesis", "name": "Thesis", "max_points": 10,
            "levels": [
                {"label": "Excellent", "points": 10, "description": "Clear", "inferred": False},
                {"label": "Partial", "points": 5, "description": "Inferred", "inferred": True},
            ],
        }
    ]
}


def client_for(*replies) -> tuple[LLMClient, FakeLLMProvider, InMemoryCallRecorder]:
    provider = FakeLLMProvider(list(replies))
    recorder = InMemoryCallRecorder()
    return LLMClient(provider, recorder, base_delay=0), provider, recorder


async def test_parse_rubric_validates_and_keeps_inferred_flags() -> None:
    llm, provider, recorder = client_for(json.dumps(RUBRIC))
    rubric = await parse_rubric(llm, "Thesis (10 pts): clear argument")
    assert rubric.criteria[0].levels[1].inferred is True
    assert "Thesis (10 pts): clear argument" in provider.calls[0][1][0]["content"]
    assert recorder.calls[0].prompt_version == "rubric_parse.v1"
    assert recorder.calls[0].purpose == "rubric_parse"


async def test_parse_rubric_retries_once_with_the_validation_error() -> None:
    duplicate = {"criteria": [RUBRIC["criteria"][0], RUBRIC["criteria"][0]]}
    llm, provider, _ = client_for(json.dumps(duplicate), json.dumps(RUBRIC))
    rubric = await parse_rubric(llm, "rubric")
    assert len(rubric.criteria) == 1
    assert "duplicate criterion ids" in provider.calls[1][1][2]["content"]


async def test_parse_rubric_fails_clearly_after_one_retry() -> None:
    llm, provider, _ = client_for("{}", '{"criteria": []}')
    with pytest.raises(LLMOutputError):
        await parse_rubric(llm, "rubric")
    assert len(provider.calls) == 2


async def test_extract_requirements() -> None:
    reply = json.dumps({"requirements": [
        {"type": "word_count", "description": "800-1000 words", "min_words": 800, "max_words": 1000}
    ]})
    llm, provider, recorder = client_for(reply)
    result = await extract_requirements(llm, "Write 800-1000 words.")
    assert result.requirements[0].min_words == 800  # type: ignore[union-attr]
    assert "Write 800-1000 words." in provider.calls[0][1][0]["content"]
    assert recorder.calls[0].prompt_version == "requirements_extract.v1"


async def test_extract_requirements_may_be_empty() -> None:
    llm, _, _ = client_for('{"requirements": []}')
    assert (await extract_requirements(llm, "Write something.")).requirements == []
