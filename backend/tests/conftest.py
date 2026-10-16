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
from app.models import Base
from app.services.llm_client import LLMClient
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder

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


@pytest.fixture
async def client(session: AsyncSession, llm_provider: FakeLLMProvider) -> AsyncIterator[AsyncClient]:
    """API client wired to the test database and the fake LLM."""

    async def override_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_llm_client] = lambda: LLMClient(
        llm_provider, InMemoryCallRecorder(), base_delay=0
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
