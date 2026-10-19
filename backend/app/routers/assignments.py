from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_llm_client
from app.models import Assignment
from app.schemas.assignments import AssignmentCreate, AssignmentRead, StrictnessUpdate
from app.schemas.rubric import Rubric
from app.services.llm_client import LLMClient
from app.services.requirements_extractor import extract_requirements
from app.services.rubric_parser import parse_rubric

router = APIRouter(prefix="/assignments", tags=["assignments"])


async def get_assignment_or_404(
    assignment_id: int, session: AsyncSession = Depends(get_session)
) -> Assignment:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    return assignment


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    body: AssignmentCreate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Assignment:
    limit = settings.max_assignment_text_chars
    for field, value in (("instructions_text", body.instructions_text),
                         ("rubric_raw_text", body.rubric_raw_text)):
        if len(value) > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{field} is {len(value)} characters; the limit is {limit}.",
            )
    assignment = Assignment(**body.model_dump())
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
