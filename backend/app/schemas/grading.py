from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.requirements import CheckResult

Confidence = Literal["low", "medium", "high"]
Supports = Literal["met", "not_met"]


# --- What the grading LLM returns -------------------------------------------------


class EvidenceQuote(BaseModel):
    quote: str = Field(min_length=1)
    supports: Supports


class CriterionGrade(BaseModel):
    """One grading run for one criterion. `reasoning` comes first so the model thinks
    before it commits to a level."""

    criterion_id: str
    reasoning: str = Field(min_length=1)
    level_label: str
    points: float
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    confidence: Confidence


class FeedbackDraft(BaseModel):
    """What the feedback LLM returns."""

    whats_missing: str = Field(min_length=1)
    where_in_draft: str = ""
    evidence_indexes: list[int] = Field(default_factory=list)
    guiding_questions: list[str] = Field(min_length=1)

    @field_validator("guiding_questions")
    @classmethod
    def _at_most_two(cls, questions: list[str]) -> list[str]:
        return questions[:2]


# --- What we store and return ----------------------------------------------------


class VerifiedEvidence(BaseModel):
    quote: str
    supports: Supports
    # Character offsets into the submitted draft; null when the quote was not found.
    start: int | None = None
    end: int | None = None
    verified: bool


class CriterionFeedback(FeedbackDraft):
    # True when the model's feedback was unavailable or looked like drafted text,
    # and a generic rubric-based hint was used instead.
    is_fallback: bool = False


class CriterionResultRead(BaseModel):
    criterion_id: str
    name: str
    max_points: float
    median_points: float
    min_points: float
    max_points_scored: float
    uncertain: bool
    chosen_level: str | None
    confidence: str | None
    reasoning: str
    run_points: list[float]
    evidence: list[VerifiedEvidence]
    feedback: CriterionFeedback | None


class TopFix(BaseModel):
    criterion_id: str
    name: str
    points_at_stake: float
    summary: str


class OverallScore(BaseModel):
    median: float | None
    min: float | None
    max: float | None
    max_possible: float


class GradingRead(BaseModel):
    id: int
    submission_id: int
    assignment_id: int
    version_number: int
    status: str
    error: str | None
    strategy: str
    model: str
    num_runs: int
    prompt_version: str
    created_at: datetime
    overall: OverallScore
    draft_text: str
    criteria: list[CriterionResultRead]
    instruction_checks: list[CheckResult]
    top_fixes: list[TopFix]


class GradeRequest(BaseModel):
    # Overrides the configured number of grading runs for this request.
    num_runs: int | None = Field(default=None, ge=1, le=7)


class SubmissionCreate(BaseModel):
    draft_text: str = Field(min_length=1)

    @field_validator("draft_text")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("draft_text must not be blank")
        return text


class SubmissionRead(BaseModel):
    id: int
    assignment_id: int
    version_number: int
    draft_text: str
    created_at: datetime

    model_config = {"from_attributes": True}
