import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    CriterionResult,
    Grading,
    InstructionCheckResult,
    LLMCall,
    Submission,
)


async def make_graph(session: AsyncSession) -> Assignment:
    assignment = Assignment(title="Essay 1", instructions_text="Write.", rubric_raw_text="Thesis: 10")
    submission = Submission(version_number=1, draft_text="My draft.")
    grading = Grading(
        strategy="per_criterion", model="m", num_runs=3, prompt_version="grade.v1",
    )
    grading.criterion_results.append(
        CriterionResult(
            criterion_id="thesis", median_points=8, min_points=7, max_points=9,
            evidence=[{"quote": "My draft", "start": 0, "end": 8, "supports": "met"}],
        )
    )
    grading.instruction_check_results.append(
        InstructionCheckResult(requirement={"type": "min_words", "value": 500}, passed=False)
    )
    submission.gradings.append(grading)
    assignment.submissions.append(submission)
    session.add(assignment)
    await session.commit()
    return assignment


async def test_defaults_and_jsonb_round_trip(session: AsyncSession) -> None:
    assignment = await make_graph(session)
    session.expire_all()
    loaded = (await session.execute(select(Assignment))).scalar_one()
    assert loaded.id == assignment.id
    assert loaded.rubric_confirmed is False and loaded.rubric_parsed is None
    assert loaded.created_at is not None

    result = (await session.execute(select(CriterionResult))).scalar_one()
    assert result.evidence[0]["supports"] == "met"
    assert result.uncertain is False
    grading = (await session.execute(select(Grading))).scalar_one()
    assert grading.status == "pending"


async def test_version_numbers_are_unique_per_assignment(session: AsyncSession) -> None:
    assignment = await make_graph(session)
    session.add(Submission(assignment_id=assignment.id, version_number=1, draft_text="dup"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_assignment_cascades(session: AsyncSession) -> None:
    assignment = await make_graph(session)
    await session.delete(assignment)
    await session.commit()
    for model in (Submission, Grading, CriterionResult, InstructionCheckResult):
        assert (await session.execute(select(func.count()).select_from(model))).scalar_one() == 0


async def test_llm_call_survives_grading_deletion(session: AsyncSession) -> None:
    assignment = await make_graph(session)
    grading = (await session.execute(select(Grading))).scalar_one()
    session.add(
        LLMCall(grading_id=grading.id, purpose="grade", model="m", prompt_version="v1", success=True)
    )
    await session.commit()
    await session.delete(assignment)
    await session.commit()
    call = (await session.execute(select(LLMCall))).scalar_one()
    assert call.grading_id is None
