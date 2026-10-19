from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.requirements import RequirementList
from app.schemas.rubric import Rubric
from app.schemas.strictness import Strictness

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class AssignmentCreate(BaseModel):
    title: ProjectName
    instructions_text: NonEmptyText
    rubric_raw_text: NonEmptyText
    teacher_strictness: Strictness = "standard"


class ProjectRename(BaseModel):
    title: ProjectName


class StrictnessUpdate(BaseModel):
    teacher_strictness: Strictness


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    instructions_text: str
    rubric_raw_text: str
    rubric_parsed: Rubric | None
    rubric_confirmed: bool
    requirements_parsed: RequirementList | None
    teacher_strictness: Strictness
    created_at: datetime


class ProjectLatest(BaseModel):
    """The newest graded attempt of a project."""

    version_number: int
    median: float
    min: float
    max: float
    max_possible: float
    # Change from the graded attempt before it; None when there is no earlier graded attempt.
    change: float | None


class ProjectSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    rubric_confirmed: bool
    teacher_strictness: Strictness
    attempts: int
    graded_attempts: int
    latest: ProjectLatest | None
