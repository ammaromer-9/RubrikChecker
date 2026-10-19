"""Dashboard summaries: one line per project with its newest score."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, Grading, Submission
from app.schemas.assignments import ProjectLatest, ProjectSummary
from app.schemas.rubric import Rubric


def _max_possible(assignment: Assignment) -> float:
    if not assignment.rubric_parsed:
        return 0.0
    return Rubric.model_validate(assignment.rubric_parsed).total_points


async def summarize_projects(session: AsyncSession, assignments: list[Assignment]) -> list[ProjectSummary]:
    if not assignments:
        return []
    ids = [a.id for a in assignments]

    attempts = dict(
        (
            await session.execute(
                select(Submission.assignment_id, func.count())
                .where(Submission.assignment_id.in_(ids))
                .group_by(Submission.assignment_id)
            )
        ).all()
    )

    # Newest complete grading of each submission (later grading ids win).
    rows = (
        await session.execute(
            select(
                Submission.assignment_id, Submission.id, Submission.version_number,
                Grading.overall_median, Grading.overall_min, Grading.overall_max,
            )
            .join(Grading, Grading.submission_id == Submission.id)
            .where(Submission.assignment_id.in_(ids), Grading.status == "complete")
            .order_by(Grading.id)
        )
    ).all()
    newest_per_submission: dict[int, tuple] = {row[1]: row for row in rows}
    graded: dict[int, list[tuple]] = {}
    for row in newest_per_submission.values():
        graded.setdefault(row[0], []).append(row)

    summaries = []
    for assignment in assignments:
        versions = sorted(graded.get(assignment.id, []), key=lambda row: row[2])
        latest = None
        if versions:
            _, _, number, median, low, high = versions[-1]
            previous = versions[-2][3] if len(versions) > 1 else None
            latest = ProjectLatest(
                version_number=number, median=median, min=low, max=high,
                max_possible=_max_possible(assignment),
                change=None if previous is None else median - previous,
            )
        summaries.append(
            ProjectSummary(
                id=assignment.id, title=assignment.title, created_at=assignment.created_at,
                rubric_confirmed=assignment.rubric_confirmed,
                teacher_strictness=assignment.teacher_strictness,  # type: ignore[arg-type]
                attempts=attempts.get(assignment.id, 0), graded_attempts=len(versions), latest=latest,
            )
        )
    return summaries
