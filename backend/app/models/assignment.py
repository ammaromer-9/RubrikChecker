from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column

if TYPE_CHECKING:
    from app.models.submission import Submission


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    instructions_text: Mapped[str] = mapped_column(Text)
    rubric_raw_text: Mapped[str] = mapped_column(Text)
    # Structured rubric produced by the parser, then edited by the user.
    rubric_parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Grading only ever uses the rubric once the user has confirmed it.
    rubric_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Checkable requirements extracted from the instructions (word count, headings, ...).
    requirements_parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # How tough the teacher is: lenient | standard | strict. Nudges borderline grading calls.
    teacher_strictness: Mapped[str] = mapped_column(Text, default="standard", server_default="standard")
    created_at: Mapped[datetime] = created_at_column()

    submissions: Mapped[list[Submission]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Submission.version_number",
    )
