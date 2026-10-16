import json

from httpx import AsyncClient

from app.services.llm_client import LLMConfigError, TransientLLMError
from app.services.llm_testing import FakeLLMProvider
from tests.test_parsers import RUBRIC

NEW = {"title": "Essay 1", "instructions_text": "Write 500 words.", "rubric_raw_text": "Thesis: 10"}


async def create(client: AsyncClient) -> int:
    response = await client.post("/api/assignments", json=NEW)
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_and_read(client: AsyncClient) -> None:
    assignment_id = await create(client)
    body = (await client.get(f"/api/assignments/{assignment_id}")).json()
    assert body["title"] == "Essay 1"
    assert body["rubric_parsed"] is None and body["rubric_confirmed"] is False


async def test_create_rejects_blank_and_oversized_text(client: AsyncClient) -> None:
    blank = await client.post("/api/assignments", json={**NEW, "rubric_raw_text": "   "})
    assert blank.status_code == 422
    huge = await client.post("/api/assignments", json={**NEW, "instructions_text": "x" * 20_001})
    assert huge.status_code == 413


async def test_unknown_assignment_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/assignments/999")).status_code == 404
    assert (await client.post("/api/assignments/999/parse-rubric")).status_code == 404


async def test_parse_then_confirm_rubric(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    assignment_id = await create(client)
    llm_provider.add_replies(json.dumps(RUBRIC))

    parsed = (await client.post(f"/api/assignments/{assignment_id}/parse-rubric")).json()
    assert parsed["rubric_parsed"]["criteria"][0]["id"] == "thesis"
    assert parsed["rubric_confirmed"] is False

    edited = json.loads(json.dumps(RUBRIC))
    edited["criteria"][0]["max_points"] = 20
    confirmed = (await client.put(f"/api/assignments/{assignment_id}/rubric", json=edited)).json()
    assert confirmed["rubric_confirmed"] is True
    assert confirmed["rubric_parsed"]["criteria"][0]["max_points"] == 20


async def test_reparsing_unconfirms_the_rubric(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    assignment_id = await create(client)
    await client.put(f"/api/assignments/{assignment_id}/rubric", json=RUBRIC)
    llm_provider.add_replies(json.dumps(RUBRIC))
    body = (await client.post(f"/api/assignments/{assignment_id}/parse-rubric")).json()
    assert body["rubric_confirmed"] is False


async def test_invalid_edited_rubric_is_rejected(client: AsyncClient) -> None:
    assignment_id = await create(client)
    response = await client.put(f"/api/assignments/{assignment_id}/rubric", json={"criteria": []})
    assert response.status_code == 422


async def test_unusable_model_output_is_a_clear_502(
    client: AsyncClient, llm_provider: FakeLLMProvider
) -> None:
    assignment_id = await create(client)
    llm_provider.add_replies("nonsense", "still nonsense")
    response = await client.post(f"/api/assignments/{assignment_id}/parse-rubric")
    assert response.status_code == 502
    assert "could not use" in response.json()["detail"]
    after = (await client.get(f"/api/assignments/{assignment_id}")).json()
    assert after["rubric_parsed"] is None  # nothing half-saved


async def test_llm_outage_is_503(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    assignment_id = await create(client)
    llm_provider.add_replies(*[TransientLLMError("429")] * 4)
    response = await client.post(f"/api/assignments/{assignment_id}/parse-rubric")
    assert response.status_code == 503


async def test_unconfigured_llm_is_503(client: AsyncClient) -> None:
    from app.deps import get_llm_client
    from app.main import app

    def broken():
        raise LLMConfigError("ANTHROPIC_API_KEY missing")

    app.dependency_overrides[get_llm_client] = broken
    assignment_id = await create(client)
    response = await client.post(f"/api/assignments/{assignment_id}/parse-rubric")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


async def test_extract_requirements_endpoint(
    client: AsyncClient, llm_provider: FakeLLMProvider
) -> None:
    assignment_id = await create(client)
    llm_provider.add_replies(json.dumps({"requirements": [
        {"type": "word_count", "description": "500+", "min_words": 500}
    ]}))
    body = (await client.post(f"/api/assignments/{assignment_id}/extract-requirements")).json()
    assert body["requirements_parsed"]["requirements"][0]["min_words"] == 500
