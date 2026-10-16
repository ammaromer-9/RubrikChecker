from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_llm_client
from app.models import Assignment, Submission
from app.routers.assignments import get_assignment_or_404
from app.schemas.grading import GradeRequest, GradingRead, SubmissionCreate, SubmissionRead
from app.services.grader import RubricNotConfirmedError, run_grading
from app.services.grading_view import build_grading_read, load_grading
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
    latest = await session.scalar(
        select(func.max(Submission.version_number)).where(Submission.assignment_id == assignment.id)
    )
    submission = Submission(
        assignment_id=assignment.id, version_number=(latest or 0) + 1, draft_text=body.draft_text
    )
    session.add(submission)
    await session.commit()
    return submission


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
