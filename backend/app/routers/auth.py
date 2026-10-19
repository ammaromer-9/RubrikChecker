from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead
from app.security import get_current_user
from app.services.auth import (
    COOKIE_NAME,
    create_session,
    end_session,
    is_valid_email,
    normalize_email,
)
from app.services.passwords import burn_time_async, hash_password_async, verify_password_async
from app.services.ratelimit import limiters

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Behind a proxy this is the proxy's address. See the deployment notes.
    return request.client.host if request.client else "unknown"


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,  # not readable by page scripts, so XSS cannot steal it
        samesite="lax",  # not sent on cross-site POSTs, which blocks CSRF
        secure=settings.cookie_secure,
        path="/",
    )


def _too_many(seconds: int) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Try again in {max(1, seconds // 60)} minute(s).",
        headers={"Retry-After": str(seconds)},
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-ups are closed on this site.")
    ip = _client_ip(request)
    if limiters.register_by_ip.blocked(ip):
        raise _too_many(limiters.register_by_ip.retry_after(ip))

    email = normalize_email(body.email)
    if not is_valid_email(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid email address.")
    if body.password.lower() == email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Your password can't be your email address.")
    limiters.register_by_ip.hit(ip)

    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email,
        display_name=body.display_name,
        password_hash=await hash_password_async(body.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # two sign-ups with the same email at the same instant
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.") from None
    _set_cookie(response, await create_session(session, user, settings.session_days), settings)
    return user


@router.post("/login", response_model=UserRead)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    email, ip = normalize_email(body.email), _client_ip(request)
    for limiter, key in ((limiters.login_by_email, email), (limiters.login_by_ip, ip)):
        if limiter.blocked(key):
            raise _too_many(limiter.retry_after(key))

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        await burn_time_async()  # same cost as a real check
        valid = False
    else:
        valid = await verify_password_async(body.password, user.password_hash)
    if not valid or user is None:
        limiters.login_by_email.hit(email)
        limiters.login_by_ip.hit(ip)
        # The same message either way, so the form can't be used to find out who has an account.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    limiters.login_by_email.reset(email)
    _set_cookie(response, await create_session(session, user, settings.session_days), settings)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> None:
    await end_session(session, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
