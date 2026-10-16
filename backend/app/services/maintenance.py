"""Housekeeping that runs at startup."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Grading

logger = logging.getLogger(__name__)


async def fail_stale_gradings(
    session_factory: async_sessionmaker[AsyncSession], older_than_minutes: int
) -> int:
    """Mark gradings stuck in "running" as failed.

    Grading runs inside a request, so a server restart mid-grade would otherwise leave
    the row "running" forever. The age threshold keeps a restart of one instance from
    failing a grading that another instance is still working on.
    """
    async with session_factory() as session:
        result = await session.execute(
            update(Grading)
            .where(
                Grading.status == "running",
                Grading.created_at < func.now() - timedelta(minutes=older_than_minutes),
            )
            .values(status="failed", error="Grading was interrupted before it finished. Please try again.")
        )
        await session.commit()
    count = result.rowcount or 0  # type: ignore[attr-defined]
    if count:
        logger.warning("Marked %d stale grading(s) as failed", count)
    return count
