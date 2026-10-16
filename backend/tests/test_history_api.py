import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Grading
from app.services.llm_client import TransientLLMError
from app.services.llm_testing import FakeLLMProvider
from tests.grading_script import DRAFT, RUBRIC, grade_reply
from tests.test_grading_flow import script, setup_submission


async def add_version(client: AsyncClient, assignment_id: int, draft: str = DRAFT) -> int:
    response = await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": draft})
    assert response.status_code == 201
    return response.json()["id"]


async def grade(client: AsyncClient, provider: FakeLLMProvider, submission_id: int, thesis: int, support: int) -> dict:
    script(provider, grades={"thesis": [grade_reply("thesis", thesis)], "support": [grade_reply("support", support)]})
    response = await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def two_versions(client: AsyncClient, llm_provider: FakeLLMProvider) -> dict:
    first = await setup_submission(client)
    assignment_id = (await client.get(f"/api/submissions/{first}")).json()["assignment_id"]
    first_grading = await grade(client, llm_provider, first, thesis=5, support=3)
    second = await add_version(client, assignment_id, DRAFT + "\n\nA stronger conclusion.")
    second_grading = await grade(client, llm_provider, second, thesis=10, support=6)
    return {"assignment_id": assignment_id, "first": first, "second": second,
            "first_grading": first_grading, "second_grading": second_grading}


async def test_compare_shows_changes_and_resolved_issues(client: AsyncClient, two_versions: dict) -> None:
    v = two_versions
    response = await client.get(f"/api/submissions/{v['second']}/compare/{v['first']}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["previous"]["version_number"] == 1 and body["current"]["version_number"] == 2
    assert body["overall"] == {
        "previous_median": 8.0, "current_median": 16.0, "change": 8.0,
        "previous_min": 8.0, "previous_max": 8.0, "current_min": 16.0, "current_max": 16.0,
        "max_possible": 16.0, "ranges_overlap": False,
    }
    by_id = {c["criterion_id"]: c for c in body["criteria"]}
    assert by_id["thesis"]["status"] == "improved" and by_id["thesis"]["change"] == 5
    assert by_id["support"]["resolved"] is True

    # Both criteria reached full marks; each had feedback last time.
    assert {r["criterion_id"] for r in body["resolved_issues"]} == {"thesis", "support"}
    assert all(r["issue"] for r in body["resolved_issues"])
    assert body["remaining_fixes"] == []
    assert body["improved_count"] == 2


async def test_compare_can_show_a_regression(client: AsyncClient, two_versions: dict) -> None:
    v = two_versions
    body = (await client.get(f"/api/submissions/{v['first']}/compare/{v['second']}")).json()
    assert body["overall"]["change"] == -8
    assert body["declined_count"] == 2 and body["resolved_issues"] == []


async def test_compare_validation(client: AsyncClient, llm_provider: FakeLLMProvider, two_versions: dict) -> None:
    v = two_versions
    same = await client.get(f"/api/submissions/{v['first']}/compare/{v['first']}")
    assert same.status_code == 400

    assert (await client.get(f"/api/submissions/{v['first']}/compare/9999")).status_code == 404
    assert (await client.get(f"/api/submissions/9999/compare/{v['first']}")).status_code == 404

    ungraded = await add_version(client, v["assignment_id"])
    conflict = await client.get(f"/api/submissions/{ungraded}/compare/{v['first']}")
    assert conflict.status_code == 409 and "Version 3 has not been graded" in conflict.json()["detail"]

    other = await setup_submission(client)
    mismatch = await client.get(f"/api/submissions/{other}/compare/{v['first']}")
    assert mismatch.status_code == 400 and "different assignments" in mismatch.json()["detail"]


async def test_history_lists_versions_with_scores(client: AsyncClient, two_versions: dict) -> None:
    v = two_versions
    history = (await client.get(f"/api/assignments/{v['assignment_id']}/history")).json()
    assert history["title"] == "Essay" and history["max_possible"] == 16
    assert [c["criterion_id"] for c in history["criteria"]] == ["thesis", "support"]
    first, second = history["versions"]
    assert (first["version_number"], second["version_number"]) == (1, 2)
    assert first["grading"]["criterion_points"] == {"thesis": 5, "support": 3}
    assert second["grading"]["overall"]["median"] == 16
    assert second["grading"]["grading_id"] == v["second_grading"]["id"]


async def test_history_uses_latest_complete_grading_and_ignores_failures(
    client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession
) -> None:
    submission = await setup_submission(client)
    assignment_id = (await client.get(f"/api/submissions/{submission}")).json()["assignment_id"]
    await grade(client, llm_provider, submission, thesis=0, support=0)
    regraded = await grade(client, llm_provider, submission, thesis=10, support=6)

    script(llm_provider, grades={"thesis": [TransientLLMError("down")], "support": [grade_reply("support", 6)]})
    assert (await client.post(f"/api/submissions/{submission}/grade", json={"num_runs": 1})).status_code == 503
    assert sorted(g.status for g in (await session.execute(select(Grading))).scalars()) == [
        "complete", "complete", "failed"
    ]

    version = (await client.get(f"/api/assignments/{assignment_id}/history")).json()["versions"][0]
    assert version["grading"]["grading_id"] == regraded["id"]
    assert version["grading"]["overall"]["median"] == 16


async def test_history_includes_ungraded_versions(client: AsyncClient) -> None:
    submission = await setup_submission(client)
    assignment_id = (await client.get(f"/api/submissions/{submission}")).json()["assignment_id"]
    history = (await client.get(f"/api/assignments/{assignment_id}/history")).json()
    assert history["versions"][0]["grading"] is None
    assert history["max_possible"] == sum(c["max_points"] for c in RUBRIC["criteria"])


async def test_history_unknown_assignment_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/assignments/999/history")).status_code == 404
