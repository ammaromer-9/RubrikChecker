from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_llm_client
from app.models import Assignment, Submission
from app.routers.assignments import get_assignment_or_404
from app.schemas.comparison import ComparisonRead, HistoryCriterion, HistoryRead
from app.schemas.grading import GradeRequest, GradingRead, SubmissionCreate, SubmissionRead
from app.schemas.rubric import Rubric
from app.services.comparison import build_history, compare_gradings
from app.services.grader import RubricNotConfirmedError, run_grading
from app.services.grading_view import (
    build_grading_read,
    load_grading,
    load_latest_complete_gradings,
)
from app.services.llm_client import LLMClient

router = APIRouter(tags=["submissions"])


async def get_submission_or_404(
    submission_id: int, session: AsyncSession = Depends(get_session)
) -> Submission:
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found.")
    return submission


@router.post(
    "/assignments/{assignment_id}/submissions",
    response_model=SubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_submission(
    body: SubmissionCreate,
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Submission:
    """Add a draft. Each call creates the next version for this assignment."""
    if len(body.draft_text) > settings.max_draft_chars:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Draft is {len(body.draft_text)} characters; the limit is {settings.max_draft_chars}.",
        )
    # Two drafts submitted at the same instant can pick the same version number; the
    # unique constraint catches that and we retry with the next number.
    assignment_id = assignment.id  # read now: a rollback expires the ORM object
    for _ in range(3):
        latest = await session.scalar(
            select(func.max(Submission.version_number)).where(
                Submission.assignment_id == assignment_id
            )
        )
        submission = Submission(
            assignment_id=assignment_id,
            version_number=(latest or 0) + 1,
            draft_text=body.draft_text,
        )
        session.add(submission)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            continue
        return submission
    raise HTTPException(
        status.HTTP_409_CONFLICT, "Several drafts were submitted at once. Please try again."
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
async def read_submission(
    submission: Submission = Depends(get_submission_or_404),
) -> Submission:
    return submission


@router.post("/submissions/{submission_id}/grade", response_model=GradingRead)
async def grade_submission(
    body: GradeRequest | None = None,
    submission: Submission = Depends(get_submission_or_404),
    session: AsyncSession = Depends(get_session),
    llm: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> GradingRead:
    """Grade synchronously. The work lives in `run_grading`, which a background worker
    could call later without changes."""
    assignment = await session.get(Assignment, submission.assignment_id)
    assert assignment is not None
    try:
        grading = await run_grading(
            session, llm, assignment, submission, settings,
            num_runs=body.num_runs if body else None,
        )
    except RubricNotConfirmedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    loaded = await load_grading(session, grading.id)
    assert loaded is not None
    return build_grading_read(loaded)


@router.get("/assignments/{assignment_id}/history", response_model=HistoryRead)
async def read_history(
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
) -> HistoryRead:
    """Every submitted version with its latest complete grading, for score trends."""
    submissions = (
        await session.execute(
            select(Submission)
            .where(Submission.assignment_id == assignment.id)
            .order_by(Submission.version_number)
        )
    ).scalars().all()
    gradings = await load_latest_complete_gradings(session, assignment.id)
    rubric = Rubric.model_validate(assignment.rubric_parsed) if assignment.rubric_parsed else None
    return build_history(
        assignment_id=assignment.id,
        title=assignment.title,
        rubric_criteria=[
            HistoryCriterion(criterion_id=c.id, name=c.name, max_points=c.max_points)
            for c in (rubric.criteria if rubric else [])
        ],
        submissions=list(submissions),
        gradings={sid: build_grading_read(g) for sid, g in gradings.items()},
    )


@router.get("/submissions/{submission_id}/compare/{previous_id}", response_model=ComparisonRead)
async def compare_submissions(
    previous_id: int,
    submission: Submission = Depends(get_submission_or_404),
    session: AsyncSession = Depends(get_session),
) -> ComparisonRead:
    """Compare this version's latest grading with an earlier version's."""
    if previous_id == submission.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose two different versions to compare.")
    previous = await session.get(Submission, previous_id)
    if previous is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Previous submission not found.")
    if previous.assignment_id != submission.assignment_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "These drafts belong to different assignments."
        )
    gradings = await load_latest_complete_gradings(session, submission.assignment_id)
    for version in (previous, submission):
        if version.id not in gradings:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Version {version.version_number} has not been graded yet.",
            )
    return compare_gradings(
        build_grading_read(gradings[previous.id]), build_grading_read(gradings[submission.id])
    )
