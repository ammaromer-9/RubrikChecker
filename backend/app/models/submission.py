from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.grading import Grading


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int]
    draft_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    gradings: Mapped[list[Grading]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Grading.id",
    )
