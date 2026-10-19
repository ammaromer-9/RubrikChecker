"""Sessions: an opaque random token in a cookie; only its hash is stored."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession, User

COOKIE_NAME = "rubriccheck_session"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(_EMAIL_RE.match(email))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


async def create_session(db: AsyncSession, user: User, days: int) -> str:
    """Create a session for `user` and return the token to put in the cookie."""
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=days),
        )
    )
    # Tidy up: forget sessions that have expired.
    await db.execute(delete(AuthSession).where(AuthSession.expires_at < datetime.now(UTC)))
    await db.commit()
    return token


async def user_for_token(db: AsyncSession, token: str | None) -> User | None:
    if not token:
        return None
    result = await db.execute(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == _hash_token(token), AuthSession.expires_at > datetime.now(UTC))
    )
    return result.scalar_one_or_none()


async def end_session(db: AsyncSession, token: str | None) -> None:
    if token:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
        await db.commit()
