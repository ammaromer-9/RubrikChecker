from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.grading import GradingRead
from app.services.grading_view import build_grading_read, load_grading

router = APIRouter(prefix="/gradings", tags=["gradings"])


@router.get("/{grading_id}", response_model=GradingRead)
async def read_grading(
    grading_id: int, session: AsyncSession = Depends(get_session)
) -> GradingRead:
    grading = await load_grading(session, grading_id)
    if grading is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grading not found.")
    return build_grading_read(grading)
