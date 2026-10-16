from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.grading import OverallScore, TopFix

ChangeStatus = Literal["improved", "declined", "unchanged", "new", "removed"]
RequirementStatus = Literal[
    "resolved", "regressed", "still_failing", "still_passing", "new", "removed"
]


class VersionRef(BaseModel):
    submission_id: int
    version_number: int
    grading_id: int


class OverallChange(BaseModel):
    previous_median: float
    current_median: float
    change: float
    previous_min: float
    previous_max: float
    current_min: float
    current_max: float
    max_possible: float
    # True when the two score ranges overlap: the change may just be grader noise.
    ranges_overlap: bool


class CriterionChange(BaseModel):
    criterion_id: str
    name: str
    max_points: float
    previous_points: float | None
    current_points: float | None
    change: float | None
    status: ChangeStatus
    ranges_overlap: bool
    uncertain: bool
    # Lost points before and has full marks now.
    resolved: bool
    # Why points were lost last time (the previous feedback), when there was any.
    issue: str | None


class ResolvedIssue(BaseModel):
    criterion_id: str
    name: str
    issue: str
    points_gained: float


class RequirementChange(BaseModel):
    description: str
    previously_passed: bool | None
    now_passed: bool | None
    status: RequirementStatus
    details: str


class ComparisonRead(BaseModel):
    assignment_id: int
    previous: VersionRef
    current: VersionRef
    overall: OverallChange
    criteria: list[CriterionChange]
    resolved_issues: list[ResolvedIssue]
    requirement_changes: list[RequirementChange]
    # What is still costing the most points in the current version.
    remaining_fixes: list[TopFix]
    improved_count: int
    declined_count: int
    unchanged_count: int


class HistoryCriterion(BaseModel):
    criterion_id: str
    name: str
    max_points: float


class HistoryGrading(BaseModel):
    grading_id: int
    overall: OverallScore
    criterion_points: dict[str, float]
    uncertain: list[str]


class HistoryVersion(BaseModel):
    submission_id: int
    version_number: int
    created_at: datetime
    grading: HistoryGrading | None


class HistoryRead(BaseModel):
    assignment_id: int
    title: str
    max_possible: float | None
    criteria: list[HistoryCriterion]
    versions: list[HistoryVersion]
