import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CriterionResult, Grading, InstructionCheckResult
from app.services.llm_client import LLMError, TransientLLMError
from app.services.llm_testing import FakeLLMProvider
from tests.grading_script import DRAFT, RUBRIC, ScriptedLLM, feedback_reply, grade_reply

REAL_QUOTE = "Many students scroll   late at night."  # extra spaces: still verifiable
FAKE_QUOTE = "Teenagers always sleep eight hours."


async def setup_submission(client: AsyncClient, confirm: bool = True, draft: str = DRAFT) -> int:
    created = await client.post("/api/assignments", json={
        "title": "Essay", "instructions_text": "Write at least 5 words.", "rubric_raw_text": "raw",
    })
    assignment_id = created.json()["id"]
    if confirm:
        assert (await client.put(f"/api/assignments/{assignment_id}/rubric", json=RUBRIC)).status_code == 200
    submission = await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": draft})
    assert submission.status_code == 201
    return submission.json()["id"]


def script(llm_provider: FakeLLMProvider, **kwargs) -> ScriptedLLM:
    scripted = ScriptedLLM(**kwargs)
    llm_provider.use_handler(scripted.handler)
    return scripted


def evidence(*pairs: tuple[str, str]) -> list[dict]:
    return [{"quote": q, "supports": s} for q, s in pairs]


async def test_full_grading_flow(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    script(
        llm_provider,
        grades={
            # thesis: 10, 10, 5 -> median 10, adjacent levels, certain
            "thesis": [grade_reply("thesis", 10), grade_reply("thesis", 10), grade_reply("thesis", 5)],
            # support: 3, 6, 0 -> median 3, spans three levels -> uncertain
            "support": [
                grade_reply("support", 3, evidence(("Many students scroll late at night.", "not_met"),
                                                   (FAKE_QUOTE, "met"))),
                grade_reply("support", 6),
                grade_reply("support", 0),
            ],
        },
        requirements='{"requirements": [{"type": "word_count", "description": "5+ words", "min_words": 5}]}',
    )
    submission_id = await setup_submission(client)

    response = await client.post(f"/api/submissions/{submission_id}/grade")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "complete" and body["num_runs"] == 3
    assert body["overall"] == {"median": 13.0, "min": 5.0, "max": 16.0, "max_possible": 16.0}
    assert body["prompt_version"] == "grade_criterion.v2+feedback.v1"

    thesis, support = body["criteria"]
    assert (thesis["median_points"], thesis["min_points"], thesis["max_points_scored"]) == (10, 5, 10)
    assert thesis["uncertain"] is False and thesis["feedback"] is None
    assert support["uncertain"] is True and support["run_points"] == [3, 6, 0]
    assert support["name"] == "Evidence & Support" and support["max_points"] == 6

    # Evidence comes from the run closest to the median (the first support run).
    real, fake = support["evidence"]
    assert real["verified"] and DRAFT[real["start"]:real["end"]] == "Many students scroll late at night."
    assert not fake["verified"] and fake["start"] is None

    # Feedback only for the criterion that lost points; bad evidence index dropped.
    assert support["feedback"]["is_fallback"] is False
    assert support["feedback"]["evidence_indexes"] == [1]
    assert len(support["feedback"]["guiding_questions"]) == 1

    assert [f["criterion_id"] for f in body["top_fixes"]] == ["support"]
    assert body["top_fixes"][0]["points_at_stake"] == 3

    (check,) = body["instruction_checks"]
    assert check["passed"] is True and check["requirement"]["type"] == "word_count"

    again = await client.get(f"/api/gradings/{body['id']}")
    assert again.status_code == 200
    assert again.json() == body


async def test_rows_are_persisted(client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession) -> None:
    script(llm_provider, grades={"thesis": [grade_reply("thesis", 5)], "support": [grade_reply("support", 6)]})
    submission_id = await setup_submission(client)
    await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 2})

    grading = (await session.execute(select(Grading))).scalar_one()
    assert grading.status == "complete" and grading.num_runs == 2
    assert (grading.overall_median, grading.overall_min, grading.overall_max) == (11, 11, 11)
    rows = (await session.execute(select(CriterionResult))).scalars().all()
    assert {r.criterion_id: r.run_points for r in rows} == {"thesis": [5, 5], "support": [6, 6]}
    assert (await session.execute(select(InstructionCheckResult))).scalars().all() == []


async def test_requirements_extracted_during_grading_are_saved(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    script(llm_provider, grades={"thesis": [grade_reply("thesis", 10)], "support": [grade_reply("support", 6)]},
           requirements='{"requirements": [{"type": "min_citations", "description": "2 cites", "count": 2}]}')
    submission_id = await setup_submission(client)
    body = (await client.post(f"/api/submissions/{submission_id}/grade")).json()
    assert body["instruction_checks"][0]["passed"] is False
    assignment = (await client.get(f"/api/assignments/{body['assignment_id']}")).json()
    assert assignment["requirements_parsed"]["requirements"][0]["count"] == 2


async def test_grading_requires_a_confirmed_rubric(client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession) -> None:
    script(llm_provider, grades={})
    submission_id = await setup_submission(client, confirm=False)
    response = await client.post(f"/api/submissions/{submission_id}/grade")
    assert response.status_code == 409 and "Confirm the rubric" in response.json()["detail"]
    assert (await session.execute(select(Grading))).scalars().all() == []


async def test_a_criterion_with_no_successful_runs_fails_the_grading(
    client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession
) -> None:
    script(llm_provider, grades={
        "thesis": [TransientLLMError("overloaded")],
        "support": [grade_reply("support", 6)],
    })
    submission_id = await setup_submission(client)
    response = await client.post(f"/api/submissions/{submission_id}/grade")
    assert response.status_code == 503
    grading = (await session.execute(select(Grading))).scalar_one()
    assert grading.status == "failed" and "overloaded" in grading.error
    assert (await session.execute(select(CriterionResult))).scalars().all() == []


async def test_some_failed_runs_are_tolerated(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    script(llm_provider, grades={
        "thesis": [LLMError("bad request"), grade_reply("thesis", 10)],
        "support": [grade_reply("support", 6)],
    })
    submission_id = await setup_submission(client)
    body = (await client.post(f"/api/submissions/{submission_id}/grade")).json()
    thesis = body["criteria"][0]
    assert thesis["run_points"] == [10, 10]  # first run failed; the other two succeeded


async def test_unknown_level_label_is_corrected_via_retry(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    script(llm_provider, grades={
        "thesis": [grade_reply("thesis", 10, label="Superb"), grade_reply("thesis", 10)],
        "support": [grade_reply("support", 6)],
    })
    submission_id = await setup_submission(client)
    response = await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1})
    assert response.status_code == 200
    assert response.json()["criteria"][0]["chosen_level"] == "Excellent"
    retry_call = [c for c in llm_provider.calls if "Criterion ID: thesis" in c[1][0]["content"]][1]
    assert "level_label" in retry_call[1][2]["content"]


async def test_points_come_from_the_rubric_not_the_model(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    bad_points = json.loads(grade_reply("thesis", 10))
    bad_points["points"] = 99
    script(llm_provider, grades={"thesis": [json.dumps(bad_points)], "support": [grade_reply("support", 6)]})
    submission_id = await setup_submission(client)
    body = (await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1})).json()
    assert body["criteria"][0]["median_points"] == 10


LONG_DRAFTED = '"' + " ".join(f"invented{i}" for i in range(30)) + '"'


async def test_drafted_looking_feedback_is_regenerated(client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
    scripted = script(
        llm_provider,
        grades={"thesis": [grade_reply("thesis", 10)], "support": [grade_reply("support", 3)]},
        feedback={"Evidence & Support": [
            feedback_reply(missing=f"You could write {LONG_DRAFTED} instead."),
            feedback_reply(missing="Your evidence is general."),
        ]},
    )
    submission_id = await setup_submission(client)
    body = (await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1})).json()
    feedback = body["criteria"][1]["feedback"]
    assert feedback["is_fallback"] is False and feedback["whats_missing"] == "Your evidence is general."
    assert len(scripted.feedback_prompts) == 2
    assert "IMPORTANT: your previous reply" not in scripted.feedback_prompts[0]
    assert "IMPORTANT: your previous reply" in scripted.feedback_prompts[1]


async def test_persistently_drafted_feedback_is_replaced_by_a_generic_hint(
    client: AsyncClient, llm_provider: FakeLLMProvider
) -> None:
    script(
        llm_provider,
        grades={"thesis": [grade_reply("thesis", 10)], "support": [grade_reply("support", 3)]},
        feedback={"Evidence & Support": [feedback_reply(missing=f"Write {LONG_DRAFTED}")]},
    )
    submission_id = await setup_submission(client)
    body = (await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1})).json()
    feedback = body["criteria"][1]["feedback"]
    assert feedback["is_fallback"] is True
    assert "invented" not in json.dumps(feedback)
    assert "Strong" in feedback["whats_missing"]  # points at the rubric's next level


async def test_feedback_llm_failure_falls_back_instead_of_failing_the_grading(
    client: AsyncClient, llm_provider: FakeLLMProvider
) -> None:
    script(
        llm_provider,
        grades={"thesis": [grade_reply("thesis", 10)], "support": [grade_reply("support", 3)]},
        feedback={"Evidence & Support": [LLMError("boom")]},
    )
    submission_id = await setup_submission(client)
    response = await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1})
    assert response.status_code == 200
    assert response.json()["criteria"][1]["feedback"]["is_fallback"] is True


@pytest.mark.parametrize("payload", [{"num_runs": 0}, {"num_runs": 8}])
async def test_num_runs_is_bounded(client: AsyncClient, llm_provider: FakeLLMProvider, payload: dict) -> None:
    script(llm_provider, grades={})
    submission_id = await setup_submission(client)
    assert (await client.post(f"/api/submissions/{submission_id}/grade", json=payload)).status_code == 422
