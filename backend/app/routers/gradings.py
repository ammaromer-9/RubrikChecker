from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.schemas.grading import GradingRead
from app.security import get_current_user
from app.services.grading_view import build_grading_read, load_grading

router = APIRouter(prefix="/gradings", tags=["gradings"])


@router.get("/{grading_id}", response_model=GradingRead)
async def read_grading(
    grading_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GradingRead:
    grading = await load_grading(session, grading_id)
    # Someone else's grading gets the same 404 as a missing one.
    if grading is None or grading.submission.assignment.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grading not found.")
    return build_grading_read(grading)
