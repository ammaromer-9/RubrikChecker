"""FastAPI dependencies for the signed-in user."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.services.auth import COOKIE_NAME, user_for_token


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    user = await user_for_token(session, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in to continue.")
    return user
