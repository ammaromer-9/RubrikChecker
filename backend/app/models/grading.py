from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column

if TYPE_CHECKING:
    from app.models.submission import Submission


class Grading(Base):
    __tablename__ = "gradings"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    strategy: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    num_runs: Mapped[int]
    overall_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    # pending | running | complete | failed
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    submission: Mapped[Submission] = relationship(back_populates="gradings")
    criterion_results: Mapped[list[CriterionResult]] = relationship(
        back_populates="grading",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CriterionResult.id",
    )
    instruction_check_results: Mapped[list[InstructionCheckResult]] = relationship(
        back_populates="grading",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InstructionCheckResult.id",
    )


class CriterionResult(Base):
    __tablename__ = "criterion_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    grading_id: Mapped[int] = mapped_column(
        ForeignKey("gradings.id", ondelete="CASCADE"), index=True
    )
    criterion_id: Mapped[str] = mapped_column(Text)
    median_points: Mapped[float] = mapped_column(Float)
    min_points: Mapped[float] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    chosen_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Verified evidence quotes with character offsets into the draft.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Missing/weak, location, guiding questions. Null for criteria with full marks.
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    grading: Mapped[Grading] = relationship(back_populates="criterion_results")


class InstructionCheckResult(Base):
    __tablename__ = "instruction_check_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    grading_id: Mapped[int] = mapped_column(
        ForeignKey("gradings.id", ondelete="CASCADE"), index=True
    )
    requirement: Mapped[dict[str, Any]] = mapped_column(JSONB)
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[str] = mapped_column(Text, default="", server_default="")

    grading: Mapped[Grading] = relationship(back_populates="instruction_check_results")
