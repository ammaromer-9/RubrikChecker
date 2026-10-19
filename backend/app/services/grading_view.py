"""Build the API response for a grading from its stored rows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Grading, Submission
from app.schemas.grading import (
    CriterionFeedback,
    CriterionResultRead,
    GradingRead,
    OverallScore,
    VerifiedEvidence,
)
from app.schemas.requirements import CheckResult
from app.schemas.rubric import Rubric
from app.services.feedback import top_fixes


async def load_grading(session: AsyncSession, grading_id: int) -> Grading | None:
    result = await session.execute(
        select(Grading)
        .where(Grading.id == grading_id)
        .options(
            selectinload(Grading.criterion_results),
            selectinload(Grading.instruction_check_results),
            joinedload(Grading.submission).joinedload(Submission.assignment),
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


def build_grading_read(grading: Grading) -> GradingRead:
    submission = grading.submission
    assignment = submission.assignment
    rubric = Rubric.model_validate(assignment.rubric_parsed) if assignment.rubric_parsed else None
    by_id = {c.id: c for c in rubric.criteria} if rubric else {}

    criteria = []
    fix_inputs = []
    for row in grading.criterion_results:
        rubric_criterion = by_id.get(row.criterion_id)
        max_points = rubric_criterion.max_points if rubric_criterion else row.max_points
        feedback = CriterionFeedback.model_validate(row.feedback) if row.feedback else None
        criteria.append(
            CriterionResultRead(
                criterion_id=row.criterion_id,
                name=rubric_criterion.name if rubric_criterion else row.criterion_id,
                max_points=max_points,
                median_points=row.median_points,
                min_points=row.min_points,
                max_points_scored=row.max_points,
                uncertain=row.uncertain,
                chosen_level=row.chosen_level,
                confidence=row.confidence,
                reasoning=row.reasoning,
                run_points=row.run_points,
                evidence=[VerifiedEvidence.model_validate(e) for e in row.evidence],
                feedback=feedback,
            )
        )
        if rubric_criterion:
            fix_inputs.append((rubric_criterion, row.median_points, feedback))

    checks = [
        CheckResult.model_validate(
            {"requirement": r.requirement, "passed": r.passed, "details": r.details}
        )
        for r in grading.instruction_check_results
    ]
    return GradingRead(
        id=grading.id,
        submission_id=submission.id,
        assignment_id=assignment.id,
        version_number=submission.version_number,
        status=grading.status,
        error=grading.error,
        strategy=grading.strategy,
        model=grading.model,
        num_runs=grading.num_runs,
        prompt_version=grading.prompt_version,
        strictness=grading.strictness,  # type: ignore[arg-type]
        created_at=grading.created_at,
        overall=OverallScore(
            median=grading.overall_median,
            min=grading.overall_min,
            max=grading.overall_max,
            max_possible=rubric.total_points if rubric else 0,
        ),
        draft_text=submission.draft_text,
        criteria=criteria,
        instruction_checks=checks,
        top_fixes=top_fixes(fix_inputs),
    )




async def load_latest_complete_gradings(
    session: AsyncSession, assignment_id: int
) -> dict[int, Grading]:
    """The newest complete grading for each submission of an assignment, by submission id."""
    result = await session.execute(
        select(Grading)
        .join(Submission, Grading.submission_id == Submission.id)
        .where(Submission.assignment_id == assignment_id, Grading.status == "complete")
        .order_by(Grading.id)
        .options(
            selectinload(Grading.criterion_results),
            selectinload(Grading.instruction_check_results),
            joinedload(Grading.submission).joinedload(Submission.assignment),
        )
        .execution_options(populate_existing=True)
    )
    latest: dict[int, Grading] = {}
    for grading in result.scalars():
        latest[grading.submission_id] = grading  # ordered by id, so later gradings win
    return latest
