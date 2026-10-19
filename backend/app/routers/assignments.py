from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_llm_client
from app.models import Assignment, User
from app.schemas.assignments import (
    AssignmentCreate,
    AssignmentRead,
    ProjectRename,
    ProjectSummary,
    StrictnessUpdate,
)
from app.schemas.rubric import Rubric
from app.security import get_current_user
from app.services.llm_client import LLMClient
from app.services.projects import summarize_projects
from app.services.requirements_extractor import extract_requirements
from app.services.rubric_parser import parse_rubric

router = APIRouter(prefix="/assignments", tags=["assignments"])


async def get_assignment_or_404(
    assignment_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Assignment:
    """The project, if it exists *and* belongs to the signed-in user.

    Someone else's project gets the same 404 as a missing one, so ids can't be probed.
    """
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None or assignment.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return assignment


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[ProjectSummary]:
    """The signed-in user's projects, newest first, each with its latest score."""
    assignments = (
        await session.execute(
            select(Assignment).where(Assignment.owner_id == user.id).order_by(Assignment.id.desc())
        )
    ).scalars().all()
    return await summarize_projects(session, list(assignments))


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    body: AssignmentCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Assignment:
    owned = await session.scalar(select(func.count()).select_from(Assignment).where(Assignment.owner_id == user.id))
    if (owned or 0) >= settings.max_projects_per_user:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You have reached the limit of {settings.max_projects_per_user} projects. Delete one to add another.",
        )
    limit = settings.max_assignment_text_chars
    for field, value in (("instructions_text", body.instructions_text),
                         ("rubric_raw_text", body.rubric_raw_text)):
        if len(value) > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{field} is {len(value)} characters; the limit is {limit}.",
            )
    assignment = Assignment(**body.model_dump(), owner_id=user.id)
    session.add(assignment)
    await session.commit()
    return assignment


@router.get("/{assignment_id}", response_model=AssignmentRead)
async def read_assignment(
    assignment: Assignment = Depends(get_assignment_or_404),
) -> Assignment:
    return assignment


@router.post("/{assignment_id}/parse-rubric", response_model=AssignmentRead)
async def parse_assignment_rubric(
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
    llm: LLMClient = Depends(get_llm_client),
) -> Assignment:
    """Parse the raw rubric with the LLM. The result must be reviewed and confirmed
    (PUT /rubric) before it can be used for grading."""
    rubric = await parse_rubric(llm, assignment.rubric_raw_text)
    assignment.rubric_parsed = rubric.model_dump(mode="json")
    assignment.rubric_confirmed = False
    await session.commit()
    return assignment


@router.put("/{assignment_id}/rubric", response_model=AssignmentRead)
async def confirm_rubric(
    rubric: Rubric,
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
) -> Assignment:
    """Save the user-reviewed rubric and mark it confirmed. Grading only uses this version."""
    assignment.rubric_parsed = rubric.model_dump(mode="json")
    assignment.rubric_confirmed = True
    await session.commit()
    return assignment


@router.post("/{assignment_id}/extract-requirements", response_model=AssignmentRead)
async def extract_assignment_requirements(
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
    llm: LLMClient = Depends(get_llm_client),
) -> Assignment:
    """Extract checkable requirements (word count, sections, citations) from the instructions."""
    requirements = await extract_requirements(llm, assignment.instructions_text)
    assignment.requirements_parsed = requirements.model_dump(mode="json")
    await session.commit()
    return assignment


@router.put("/{assignment_id}/strictness", response_model=AssignmentRead)
async def set_teacher_strictness(
    body: StrictnessUpdate,
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
) -> Assignment:
    """How tough the teacher is. Applies to gradings started after this change."""
    assignment.teacher_strictness = body.teacher_strictness
    await session.commit()
    return assignment


@router.patch("/{assignment_id}", response_model=AssignmentRead)
async def rename_project(
    body: ProjectRename,
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
) -> Assignment:
    assignment.title = body.title
    await session.commit()
    return assignment


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    assignment: Assignment = Depends(get_assignment_or_404),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a project with all its attempts and gradings. This cannot be undone."""
    await session.delete(assignment)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
