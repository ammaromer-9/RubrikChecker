from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all models.

    Auth note: there are no user accounts in the MVP. To add them later, add a
    `users` table and an `owner_id` foreign key on `assignments`; everything
    else hangs off an assignment, so ownership checks stay in one place.
    """


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())
