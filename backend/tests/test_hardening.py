"""Error handling, limits, configuration validation, and startup housekeeping."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import app.main as main_module
from app.config import Settings
from app.db import get_session
from app.main import app
from app.models import Assignment, Grading, Submission
from app.services.auth import COOKIE_NAME
from app.services.maintenance import fail_stale_gradings


@pytest.fixture
async def lenient_client():
    """Like a real server: unhandled errors become 500 responses instead of test failures."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    # A cookie is needed for the request to get as far as the database.
    async with AsyncClient(transport=transport, base_url="http://test", cookies={COOKIE_NAME: "any-token"}) as c:
        yield c
    app.dependency_overrides.clear()


class BrokenSession:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def get(self, *args, **kwargs):
        raise self.error

    async def execute(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize(
    "error",
    [OperationalError("SELECT 1", {}, Exception("connection refused")), ConnectionRefusedError("refused")],
)
async def test_database_outage_is_a_clear_503(lenient_client: AsyncClient, error: Exception) -> None:
    app.dependency_overrides[get_session] = lambda: BrokenSession(error)
    response = await lenient_client.get("/api/assignments/1")
    assert response.status_code == 503
    assert "database is unavailable" in response.json()["detail"]


async def test_unexpected_errors_return_a_generic_500_without_leaking_details(lenient_client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = lambda: BrokenSession(RuntimeError("secret internal detail /etc/passwd"))
    response = await lenient_client.get("/api/assignments/1")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side. Please try again."}
    assert "secret" not in response.text


async def test_oversized_request_bodies_are_rejected_before_being_read(
    lenient_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.settings, "max_upload_bytes", 2048)  # -> ~1 MB request cap
    response = await lenient_client.post("/api/files/extract", files={"file": ("a.txt", b"x" * (2 * 1024 * 1024))})
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]

    # A small body gets past the size check (and is then asked to sign in).
    small = await lenient_client.post("/api/files/extract", files={"file": ("a.txt", b"small")})
    assert small.status_code != 413


async def test_concurrent_drafts_retry_on_a_version_number_collision(client: AsyncClient, session: AsyncSession, monkeypatch) -> None:
    assignment_id = (await client.post("/api/assignments", json={
        "title": "T", "instructions_text": "i", "rubric_raw_text": "r"})).json()["id"]
    await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": "v1"})

    real_commit = session.commit
    attempts = {"n": 0}

    async def flaky_commit() -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("duplicate version_number"))
        await real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)
    response = await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": "v2"})
    assert response.status_code == 201 and response.json()["version_number"] == 2
    assert attempts["n"] == 2


async def test_persistent_version_collisions_give_a_409(client: AsyncClient, session: AsyncSession, monkeypatch) -> None:
    assignment_id = (await client.post("/api/assignments", json={
        "title": "T", "instructions_text": "i", "rubric_raw_text": "r"})).json()["id"]

    async def always_collides() -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(session, "commit", always_collides)
    response = await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": "x"})
    assert response.status_code == 409


class TestSettingsValidation:
    @pytest.mark.parametrize(
        "bad",
        [
            {"grading_runs": 0}, {"grading_runs": 8}, {"grading_concurrency": 0},
            {"llm_max_retries": -1}, {"llm_timeout_seconds": 0}, {"max_draft_chars": 5},
            {"anthropic_effort": "extreme"}, {"log_level": "LOUD"}, {"grading_stale_minutes": 0},
        ],
    )
    def test_bad_values_fail_at_startup(self, bad: dict) -> None:
        with pytest.raises(ValidationError):
            Settings(**bad)

    def test_valid_values_are_normalised(self) -> None:
        s = Settings(anthropic_effort=" HIGH ", log_level="debug")
        assert (s.anthropic_effort, s.log_level) == ("high", "DEBUG")
        assert Settings(anthropic_effort="").anthropic_effort == ""  # empty = model default

    def test_values_come_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GRADING_RUNS", "5")
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
        s = Settings()
        assert s.grading_runs == 5 and s.cors_origin_list == ["https://a.example", "https://b.example"]

    def test_request_cap_leaves_room_for_form_overhead(self) -> None:
        s = Settings(max_upload_bytes=1024 * 1024)
        assert s.max_request_bytes == 2 * 1024 * 1024


async def test_only_old_running_gradings_are_marked_failed(session: AsyncSession) -> None:
    assignment = Assignment(title="T", instructions_text="i", rubric_raw_text="r")
    submission = Submission(version_number=1, draft_text="d")
    assignment.submissions.append(submission)
    now = datetime.now(UTC)

    def grading(status: str, age_minutes: int) -> Grading:
        return Grading(
            strategy="s", model="m", num_runs=1, prompt_version="p", status=status,
            created_at=now - timedelta(minutes=age_minutes),
        )

    submission.gradings.extend([
        grading("running", 120), grading("running", 1), grading("complete", 120), grading("failed", 120),
    ])
    session.add(assignment)
    await session.commit()

    count = await fail_stale_gradings(lambda: _same_session(session), older_than_minutes=30)
    assert count == 1

    session.expire_all()
    rows = (await session.execute(select(Grading).order_by(Grading.id))).scalars().all()
    assert [g.status for g in rows] == ["failed", "running", "complete", "failed"]
    assert "interrupted" in rows[0].error
    assert rows[1].error is None


class _same_session:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, *exc) -> None:
        return None
