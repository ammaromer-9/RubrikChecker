import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy as sa
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.config import get_settings
from app.db import get_session
from app.deps import get_llm_client
from app.main import app
from app.models import Base, User
from app.services.auth import COOKIE_NAME, create_session
from app.services.llm_client import LLMClient
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder
from app.services.ratelimit import limiters

TABLES = ", ".join(t.name for t in Base.metadata.sorted_tables)


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def migrated_test_db() -> Iterator[str]:
    """Apply Alembic migrations to the test database once per run.

    Using the real migrations (not create_all) means every DB test also checks them.
    Skips if Postgres is not reachable, e.g. `docker compose up -d db` was not run.
    """
    url = get_settings().test_database_url
    async def probe() -> None:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(probe())
    except (OperationalError, OSError) as exc:
        pytest.skip(f"Test database unreachable ({type(exc).__name__}); run docker compose up -d db")

    config = _alembic_config(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield url
    command.downgrade(config, "base")


@pytest.fixture
async def session(migrated_test_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_test_db, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def llm_provider() -> FakeLLMProvider:
    """Script replies with `llm_provider.add_replies(...)`. The real API is never called."""
    return FakeLLMProvider()


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Login and sign-up limits are process-wide; start every test with a clean slate."""
    limiters.clear()
    yield
    limiters.clear()


async def make_user(db: AsyncSession, email: str) -> tuple[User, str]:
    """A user plus a valid session token. The password hash is a placeholder (so these users
    can't log in with a password), which keeps the many API tests fast."""
    user = User(email=email, display_name="", password_hash="scrypt$placeholder")
    db.add(user)
    await db.commit()
    return user, await create_session(db, user, days=1)


def _api_client(token: str | None = None) -> AsyncClient:
    cookies = {COOKIE_NAME: token} if token else None
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=cookies)


@pytest.fixture
async def user(session: AsyncSession) -> tuple[User, str]:
    return await make_user(session, "student@example.com")


@pytest.fixture
async def client(
    session: AsyncSession, llm_provider: FakeLLMProvider, user: tuple[User, str]
) -> AsyncIterator[AsyncClient]:
    """API client signed in as `student@example.com`, wired to the test database and fake LLM."""

    async def override_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_llm_client] = lambda: LLMClient(
        llm_provider, InMemoryCallRecorder(), base_delay=0
    )
    async with _api_client(user[1]) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def other_client(session: AsyncSession, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """A second, different signed-in user (for testing that data stays private)."""
    _, token = await make_user(session, "someone.else@example.com")
    async with _api_client(token) as c:
        yield c


@pytest.fixture
async def anon_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Not signed in."""
    async with _api_client() as c:
        yield c
