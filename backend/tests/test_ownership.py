"""Every user's projects are private, and the limits that protect your API credits."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.main import app
from app.models import Assignment, Grading, Submission
from app.services.llm_testing import FakeLLMProvider
from tests.grading_script import RUBRIC, grade_reply
from tests.test_grading_flow import script

NEW = {"title": "Essay", "instructions_text": "Write.", "rubric_raw_text": "Thesis: 10"}


async def make_project(client: AsyncClient, **overrides) -> int:
    response = await client.post("/api/assignments", json={**NEW, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def graded_attempt(client: AsyncClient, provider: FakeLLMProvider, assignment_id: int, thesis: int, support: int, draft: str = "A draft") -> dict:
    script(provider, grades={"thesis": [grade_reply("thesis", thesis)], "support": [grade_reply("support", support)]})
    submission = (await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": draft})).json()["id"]
    response = await client.post(f"/api/submissions/{submission}/grade", json={"num_runs": 1})
    assert response.status_code == 200, response.text
    return {"submission": submission, "grading": response.json()}


PROTECTED = [
    ("GET", "/api/assignments"), ("POST", "/api/assignments"), ("GET", "/api/assignments/1"),
    ("PATCH", "/api/assignments/1"), ("DELETE", "/api/assignments/1"),
    ("POST", "/api/assignments/1/parse-rubric"), ("PUT", "/api/assignments/1/rubric"),
    ("PUT", "/api/assignments/1/strictness"), ("POST", "/api/assignments/1/extract-requirements"),
    ("POST", "/api/assignments/1/submissions"), ("GET", "/api/assignments/1/history"),
    ("GET", "/api/submissions/1"), ("POST", "/api/submissions/1/grade"),
    ("GET", "/api/submissions/1/compare/2"), ("GET", "/api/gradings/1"),
    ("POST", "/api/files/extract"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_everything_needs_an_account(anon_client: AsyncClient, method: str, path: str) -> None:
    response = await anon_client.request(method, path)
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


async def test_health_stays_public(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/api/health")).status_code == 200


class TestPrivacy:
    """Someone else's data gets the same 404 as data that doesn't exist."""

    @pytest.fixture
    async def theirs(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> dict:
        assignment_id = await make_project(client)
        await client.put(f"/api/assignments/{assignment_id}/rubric", json=RUBRIC)
        first = await graded_attempt(client, llm_provider, assignment_id, 5, 3)
        second = await graded_attempt(client, llm_provider, assignment_id, 10, 6, "Better")
        return {"assignment": assignment_id, "first": first, "second": second}

    async def test_the_owner_can_use_them(self, client: AsyncClient, theirs: dict) -> None:
        assert (await client.get(f"/api/assignments/{theirs['assignment']}")).status_code == 200

    async def test_other_users_cannot_read_or_change_a_project(self, other_client: AsyncClient, theirs: dict) -> None:
        a = theirs["assignment"]
        missing = await other_client.get("/api/assignments/987654")
        for method, path, body in [
            ("GET", f"/api/assignments/{a}", None),
            ("PATCH", f"/api/assignments/{a}", {"title": "Hijacked"}),
            ("DELETE", f"/api/assignments/{a}", None),
            ("POST", f"/api/assignments/{a}/parse-rubric", None),
            ("PUT", f"/api/assignments/{a}/rubric", RUBRIC),
            ("PUT", f"/api/assignments/{a}/strictness", {"teacher_strictness": "strict"}),
            ("POST", f"/api/assignments/{a}/extract-requirements", None),
            ("POST", f"/api/assignments/{a}/submissions", {"draft_text": "mine now"}),
            ("GET", f"/api/assignments/{a}/history", None),
        ]:
            response = await other_client.request(method, path, json=body)
            assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
            assert response.json() == {"detail": "Project not found."}
        assert missing.status_code == 404 and missing.json() == {"detail": "Project not found."}  # indistinguishable

    async def test_other_users_cannot_reach_attempts_or_gradings(self, other_client: AsyncClient, theirs: dict) -> None:
        s1, s2 = theirs["first"]["submission"], theirs["second"]["submission"]
        g = theirs["second"]["grading"]["id"]
        for method, path in [
            ("GET", f"/api/submissions/{s1}"), ("POST", f"/api/submissions/{s1}/grade"),
            ("GET", f"/api/submissions/{s2}/compare/{s1}"), ("GET", f"/api/gradings/{g}"),
        ]:
            assert (await other_client.request(method, path)).status_code == 404, f"{method} {path}"

    async def test_nothing_changed_after_those_attempts(self, client: AsyncClient, other_client: AsyncClient, theirs: dict, session: AsyncSession) -> None:
        a = theirs["assignment"]
        await other_client.patch(f"/api/assignments/{a}", json={"title": "Hijacked"})
        await other_client.delete(f"/api/assignments/{a}")
        assert (await client.get(f"/api/assignments/{a}")).json()["title"] == "Essay"
        assert len((await session.execute(select(Submission))).scalars().all()) == 2

    async def test_you_cannot_compare_your_attempt_with_someone_elses(self, client: AsyncClient, other_client: AsyncClient, theirs: dict, llm_provider: FakeLLMProvider) -> None:
        mine = await make_project(other_client)
        await other_client.put(f"/api/assignments/{mine}/rubric", json=RUBRIC)
        own = await graded_attempt(other_client, llm_provider, mine, 5, 3)
        response = await other_client.get(f"/api/submissions/{own['submission']}/compare/{theirs['first']['submission']}")
        assert response.status_code == 404

    async def test_project_lists_only_show_your_own(self, client: AsyncClient, other_client: AsyncClient, theirs: dict) -> None:
        assert [p["id"] for p in (await client.get("/api/assignments")).json()] == [theirs["assignment"]]
        assert (await other_client.get("/api/assignments")).json() == []

    async def test_uploaded_projects_are_owned_by_the_creator(self, client: AsyncClient, session: AsyncSession, user) -> None:
        a = await make_project(client)
        assert (await session.get(Assignment, a)).owner_id == user[0].id


class TestProjects:
    async def test_dashboard_summaries(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        empty = await make_project(client, title="Not started")
        two = await make_project(client, title="Two attempts")
        await client.put(f"/api/assignments/{two}/rubric", json=RUBRIC)
        await graded_attempt(client, llm_provider, two, 5, 3)
        await graded_attempt(client, llm_provider, two, 10, 6, "Better draft")
        await client.post(f"/api/assignments/{two}/submissions", json={"draft_text": "ungraded third"})

        projects = {p["title"]: p for p in (await client.get("/api/assignments")).json()}
        assert list(projects) == ["Two attempts", "Not started"]  # newest first
        assert (projects["Not started"]["attempts"], projects["Not started"]["latest"]) == (0, None)
        assert projects["Not started"]["id"] == empty

        p = projects["Two attempts"]
        assert (p["attempts"], p["graded_attempts"], p["rubric_confirmed"]) == (3, 2, True)
        assert p["latest"] == {"version_number": 2, "median": 16.0, "min": 16.0, "max": 16.0, "max_possible": 16.0, "change": 8.0}

    async def test_a_single_graded_attempt_has_no_change(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        a = await make_project(client)
        await client.put(f"/api/assignments/{a}/rubric", json=RUBRIC)
        await graded_attempt(client, llm_provider, a, 5, 3)
        assert (await client.get("/api/assignments")).json()[0]["latest"]["change"] is None

    async def test_regrading_does_not_double_count_an_attempt(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        a = await make_project(client)
        await client.put(f"/api/assignments/{a}/rubric", json=RUBRIC)
        first = await graded_attempt(client, llm_provider, a, 5, 3)
        await client.post(f"/api/submissions/{first['submission']}/grade", json={"num_runs": 1})
        summary = (await client.get("/api/assignments")).json()[0]
        assert summary["attempts"] == 1 and summary["graded_attempts"] == 1

    async def test_rename(self, client: AsyncClient) -> None:
        a = await make_project(client)
        response = await client.patch(f"/api/assignments/{a}", json={"title": "  Chapter 3 essay  "})
        assert response.status_code == 200 and response.json()["title"] == "Chapter 3 essay"
        assert (await client.get(f"/api/assignments/{a}")).json()["title"] == "Chapter 3 essay"

    @pytest.mark.parametrize("title", ["", "   ", "x" * 121, None])
    async def test_bad_names_are_rejected(self, client: AsyncClient, title) -> None:
        a = await make_project(client)
        assert (await client.patch(f"/api/assignments/{a}", json={"title": title})).status_code == 422
        assert (await client.post("/api/assignments", json={**NEW, "title": title})).status_code == 422

    async def test_delete_removes_the_project_and_everything_in_it(self, client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession) -> None:
        a = await make_project(client)
        await client.put(f"/api/assignments/{a}/rubric", json=RUBRIC)
        attempt = await graded_attempt(client, llm_provider, a, 5, 3)
        assert (await client.delete(f"/api/assignments/{a}")).status_code == 204
        assert (await client.get(f"/api/assignments/{a}")).status_code == 404
        assert (await client.get(f"/api/gradings/{attempt['grading']['id']}")).status_code == 404
        session.expire_all()
        assert (await session.execute(select(Submission))).scalars().all() == []
        assert (await session.execute(select(Grading))).scalars().all() == []
        assert (await client.delete(f"/api/assignments/{a}")).status_code == 404

    async def test_project_limit(self, client: AsyncClient) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_projects_per_user=2)
        try:
            await make_project(client); await make_project(client)
            response = await client.post("/api/assignments", json=NEW)
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert response.status_code == 409 and "limit of 2 projects" in response.json()["detail"]

    async def test_the_limit_is_per_user_and_freed_by_deleting(self, client: AsyncClient, other_client: AsyncClient) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_projects_per_user=1)
        try:
            first = await make_project(client)
            assert (await other_client.post("/api/assignments", json=NEW)).status_code == 201
            assert (await client.post("/api/assignments", json=NEW)).status_code == 409
            await client.delete(f"/api/assignments/{first}")
            assert (await client.post("/api/assignments", json=NEW)).status_code == 201
        finally:
            app.dependency_overrides.pop(get_settings, None)


class TestDailyGradingLimit:
    async def grade_n(self, client: AsyncClient, provider: FakeLLMProvider, n: int, first_status: int = 200) -> list[int]:
        a = await make_project(client)
        await client.put(f"/api/assignments/{a}/rubric", json=RUBRIC)
        script(provider, grades={"thesis": [grade_reply("thesis", 5)], "support": [grade_reply("support", 3)]})
        submission = (await client.post(f"/api/assignments/{a}/submissions", json={"draft_text": "d"})).json()["id"]
        return [(await client.post(f"/api/submissions/{submission}/grade", json={"num_runs": 1})).status_code for _ in range(n)]

    async def test_stops_at_the_limit_with_a_clear_message(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_gradings_per_day=2)
        try:
            statuses = await self.grade_n(client, llm_provider, 3)
            calls_before = len(llm_provider.calls)
            blocked = await client.post("/api/submissions/1/grade")
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert statuses == [200, 200, 429]
        assert blocked.status_code in (404, 429)  # (id 1 may not be this user's; the 3rd above is the real check)
        assert len(llm_provider.calls) == calls_before  # no model calls were made after the limit

    async def test_message_names_the_limit(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_gradings_per_day=1)
        try:
            a = await make_project(client)
            await client.put(f"/api/assignments/{a}/rubric", json=RUBRIC)
            script(llm_provider, grades={"thesis": [grade_reply("thesis", 5)], "support": [grade_reply("support", 3)]})
            sid = (await client.post(f"/api/assignments/{a}/submissions", json={"draft_text": "d"})).json()["id"]
            await client.post(f"/api/submissions/{sid}/grade", json={"num_runs": 1})
            response = await client.post(f"/api/submissions/{sid}/grade", json={"num_runs": 1})
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert response.status_code == 429 and "today's limit of 1 gradings" in response.json()["detail"]

    async def test_one_users_usage_does_not_block_another(self, client: AsyncClient, other_client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_gradings_per_day=1)
        try:
            assert await self.grade_n(client, llm_provider, 2) == [200, 429]
            assert await self.grade_n(other_client, llm_provider, 1) == [200]
        finally:
            app.dependency_overrides.pop(get_settings, None)

    async def test_gradings_older_than_a_day_do_not_count(self, client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(max_gradings_per_day=1)
        try:
            a = await make_project(client)
            await client.put(f"/api/assignments/{a}/rubric", json=RUBRIC)
            script(llm_provider, grades={"thesis": [grade_reply("thesis", 5)], "support": [grade_reply("support", 3)]})
            sid = (await client.post(f"/api/assignments/{a}/submissions", json={"draft_text": "d"})).json()["id"]
            assert (await client.post(f"/api/submissions/{sid}/grade", json={"num_runs": 1})).status_code == 200
            await session.execute(update(Grading).values(created_at=datetime.now(UTC) - timedelta(hours=25)))
            await session.commit()
            assert (await client.post(f"/api/submissions/{sid}/grade", json={"num_runs": 1})).status_code == 200
        finally:
            app.dependency_overrides.pop(get_settings, None)


class TestOriginCheck:
    async def test_state_changing_requests_from_unknown_sites_are_refused(self, client: AsyncClient) -> None:
        evil = {"Origin": "https://evil.example"}
        for method, path in [("POST", "/api/assignments"), ("DELETE", "/api/assignments/1"), ("PATCH", "/api/assignments/1"), ("PUT", "/api/assignments/1/strictness")]:
            response = await client.request(method, path, headers=evil, json=NEW)
            assert response.status_code == 403, f"{method} {path}"
            assert "origin" in response.json()["detail"]
        assert (await client.get("/api/assignments")).json() == []  # nothing was created

    async def test_the_real_frontend_origin_is_accepted(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.main as main_module

        # Pin the setting so the test doesn't depend on a developer's own .env.
        monkeypatch.setattr(main_module.settings, "cors_origins", "http://localhost:5173,http://127.0.0.1:5173")
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            assert (await client.post("/api/assignments", json=NEW, headers={"Origin": origin})).status_code == 201

    async def test_reads_and_requests_without_an_origin_are_not_blocked(self, client: AsyncClient) -> None:
        assert (await client.get("/api/assignments", headers={"Origin": "https://evil.example"})).status_code == 200
        assert (await client.post("/api/assignments", json=NEW)).status_code == 201

    async def test_cors_allows_credentials_only_for_known_origins(self, anon_client: AsyncClient) -> None:
        good = await anon_client.options("/api/auth/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        assert good.headers.get("access-control-allow-credentials") == "true"
        assert good.headers.get("access-control-allow-origin") == "http://localhost:5173"
        bad = await anon_client.options("/api/auth/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in bad.headers
