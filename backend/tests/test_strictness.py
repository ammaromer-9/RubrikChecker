import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.holistic import grade_holistic_runs
from app.models import Grading
from app.prompts.loader import load_prompt
from app.schemas.rubric import Rubric
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder
from app.services.strictness import guidance_for
from tests.eval_fakes import FakeGrader, make_client_factory
from tests.grading_script import RUBRIC, grade_reply
from tests.test_grading_flow import script, setup_submission

STRICT_MARK = "strict grader"
LENIENT_MARK = "lenient grader"
NEW = {"title": "T", "instructions_text": "i", "rubric_raw_text": "r"}


def grade_prompts(provider: FakeLLMProvider) -> list[str]:
    return [m[0]["content"] for _, m in provider.calls if "Criterion ID:" in m[0]["content"]]


class TestGuidance:
    def test_standard_adds_nothing(self) -> None:
        assert guidance_for("standard") == ""

    def test_strict_and_lenient_lean_in_opposite_directions(self) -> None:
        strict, lenient = guidance_for("strict"), guidance_for("lenient")
        assert "choose the lower one" in strict and "choose the higher one" in lenient
        assert STRICT_MARK in strict and LENIENT_MARK in lenient

    @pytest.mark.parametrize("level", ["strict", "lenient"])
    def test_both_keep_the_rubric_as_the_standard(self, level: str) -> None:
        text = guidance_for(level)
        assert "borderline" in text  # only borderline calls are affected
        assert "listed levels" in text or "level descriptions" in text

    def test_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown strictness"):
            guidance_for("brutal")


class TestPromptTemplates:
    @pytest.mark.parametrize("name", ["grade_criterion", "grade_criterion_no_evidence", "grade_holistic"])
    def test_every_grading_prompt_has_the_guidance_slot_and_a_new_version(self, name: str) -> None:
        prompt = load_prompt(name)
        assert prompt.version == f"{name}.v2"
        assert "$strictness_guidance" in prompt.template.template

    def test_old_prompt_versions_are_kept_for_traceability(self) -> None:
        v1 = load_prompt("grade_criterion")  # latest
        assert v1.version.endswith("v2")
        from pathlib import Path

        assert (Path(__file__).parent.parent / "app/prompts/grade_criterion.v1.txt").exists()


class TestAssignmentSetting:
    async def test_defaults_to_standard(self, client: AsyncClient) -> None:
        created = (await client.post("/api/assignments", json=NEW)).json()
        assert created["teacher_strictness"] == "standard"

    async def test_can_be_chosen_at_creation_and_changed_later(self, client: AsyncClient) -> None:
        created = (await client.post("/api/assignments", json={**NEW, "teacher_strictness": "strict"})).json()
        assert created["teacher_strictness"] == "strict"
        updated = await client.put(f"/api/assignments/{created['id']}/strictness", json={"teacher_strictness": "lenient"})
        assert updated.status_code == 200 and updated.json()["teacher_strictness"] == "lenient"
        assert (await client.get(f"/api/assignments/{created['id']}")).json()["teacher_strictness"] == "lenient"

    @pytest.mark.parametrize("bad", ["brutal", "", None, 3])
    async def test_invalid_values_are_rejected(self, client: AsyncClient, bad) -> None:
        created = (await client.post("/api/assignments", json=NEW)).json()
        response = await client.put(f"/api/assignments/{created['id']}/strictness", json={"teacher_strictness": bad})
        assert response.status_code == 422
        assert (await client.post("/api/assignments", json={**NEW, "teacher_strictness": bad})).status_code == 422

    async def test_unknown_assignment(self, client: AsyncClient) -> None:
        response = await client.put("/api/assignments/999/strictness", json={"teacher_strictness": "strict"})
        assert response.status_code == 404


class TestGrading:
    def setup_llm(self, provider: FakeLLMProvider) -> None:
        script(provider, grades={"thesis": [grade_reply("thesis", 10)], "support": [grade_reply("support", 6)]})

    async def grade(self, client: AsyncClient, submission_id: int, **body) -> dict:
        response = await client.post(f"/api/submissions/{submission_id}/grade", json={"num_runs": 1, **body})
        assert response.status_code == 200, response.text
        return response.json()

    async def make(self, client: AsyncClient, strictness: str | None = None) -> tuple[int, int]:
        submission_id = await setup_submission(client)
        assignment_id = (await client.get(f"/api/submissions/{submission_id}")).json()["assignment_id"]
        if strictness:
            await client.put(f"/api/assignments/{assignment_id}/strictness", json={"teacher_strictness": strictness})
        return assignment_id, submission_id

    async def test_standard_sends_no_extra_guidance(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        self.setup_llm(llm_provider)
        _, sid = await self.make(client)
        body = await self.grade(client, sid)
        assert body["strictness"] == "standard"
        assert grade_prompts(llm_provider) and not any("Grading style:" in p for p in grade_prompts(llm_provider))

    @pytest.mark.parametrize(("level", "marker"), [("strict", STRICT_MARK), ("lenient", LENIENT_MARK)])
    async def test_the_assignment_setting_reaches_every_grading_prompt(
        self, client: AsyncClient, llm_provider: FakeLLMProvider, level: str, marker: str
    ) -> None:
        self.setup_llm(llm_provider)
        _, sid = await self.make(client, level)
        body = await self.grade(client, sid)
        prompts = grade_prompts(llm_provider)
        assert body["strictness"] == level and len(prompts) == 2  # one per criterion
        assert all(marker in p and "Grading style:" in p for p in prompts)
        # The guidance sits with the standard, before the student's draft.
        assert all(p.index("Grading style:") < p.index("<draft>") for p in prompts)

    async def test_a_request_can_override_the_assignment_without_changing_it(
        self, client: AsyncClient, llm_provider: FakeLLMProvider, session: AsyncSession
    ) -> None:
        self.setup_llm(llm_provider)
        assignment_id, sid = await self.make(client, "strict")
        body = await self.grade(client, sid, teacher_strictness="lenient")
        assert body["strictness"] == "lenient"
        assert all(LENIENT_MARK in p and STRICT_MARK not in p for p in grade_prompts(llm_provider))
        assert (await client.get(f"/api/assignments/{assignment_id}")).json()["teacher_strictness"] == "strict"

        stored = (await session.execute(select(Grading))).scalar_one()
        assert stored.strictness == "lenient"

    async def test_regrading_with_a_new_setting_creates_a_new_grading(
        self, client: AsyncClient, llm_provider: FakeLLMProvider
    ) -> None:
        self.setup_llm(llm_provider)
        _, sid = await self.make(client)
        first = await self.grade(client, sid)
        second = await self.grade(client, sid, teacher_strictness="strict")
        assert first["id"] != second["id"]
        assert (first["strictness"], second["strictness"]) == ("standard", "strict")
        assert (await client.get(f"/api/gradings/{first['id']}")).json()["strictness"] == "standard"

    async def test_invalid_override_is_rejected_before_any_model_call(
        self, client: AsyncClient, llm_provider: FakeLLMProvider
    ) -> None:
        self.setup_llm(llm_provider)
        _, sid = await self.make(client)
        response = await client.post(f"/api/submissions/{sid}/grade", json={"teacher_strictness": "evil"})
        assert response.status_code == 422 and llm_provider.calls == []

    async def test_feedback_prompts_are_unchanged(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        script(llm_provider, grades={"thesis": [grade_reply("thesis", 5)], "support": [grade_reply("support", 3)]})
        _, sid = await self.make(client, "strict")
        await self.grade(client, sid)
        feedback = [m[0]["content"] for _, m in llm_provider.calls if "You are a coach" in m[0]["content"]]
        assert feedback and not any(STRICT_MARK in p for p in feedback)


class TestComparisonAndHistory:
    async def two_versions(self, client: AsyncClient, provider: FakeLLMProvider, first: str, second: str) -> tuple[int, int, int]:
        script(provider, grades={"thesis": [grade_reply("thesis", 5)], "support": [grade_reply("support", 3)]})
        s1 = await setup_submission(client)
        assignment_id = (await client.get(f"/api/submissions/{s1}")).json()["assignment_id"]
        s2 = (await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": "v2"})).json()["id"]
        await client.post(f"/api/submissions/{s1}/grade", json={"num_runs": 1, "teacher_strictness": first})
        await client.post(f"/api/submissions/{s2}/grade", json={"num_runs": 1, "teacher_strictness": second})
        return assignment_id, s1, s2

    async def test_flags_a_comparison_across_different_strictness(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        _, s1, s2 = await self.two_versions(client, llm_provider, "standard", "strict")
        body = (await client.get(f"/api/submissions/{s2}/compare/{s1}")).json()
        assert body["strictness_differs"] is True
        assert (body["previous"]["strictness"], body["current"]["strictness"]) == ("standard", "strict")

    async def test_no_flag_when_both_used_the_same_setting(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        _, s1, s2 = await self.two_versions(client, llm_provider, "lenient", "lenient")
        assert (await client.get(f"/api/submissions/{s2}/compare/{s1}")).json()["strictness_differs"] is False

    async def test_history_shows_each_versions_setting(self, client: AsyncClient, llm_provider: FakeLLMProvider) -> None:
        assignment_id, _, _ = await self.two_versions(client, llm_provider, "standard", "strict")
        versions = (await client.get(f"/api/assignments/{assignment_id}/history")).json()["versions"]
        assert [v["grading"]["strictness"] for v in versions] == ["standard", "strict"]


class TestEvalPaths:
    rubric = Rubric.model_validate(RUBRIC)

    async def test_holistic_grading_accepts_strictness(self) -> None:
        grader = FakeGrader({"thesis": 10, "support": 6}, quote="x")
        llm = make_client_factory(grader)(None, InMemoryCallRecorder())
        await grade_holistic_runs(llm, self.rubric, instructions="i", draft="d", num_runs=1,
                                  concurrency=1, enforce_evidence=False, strictness="strict")
        assert STRICT_MARK in grader.prompts[0]

    async def test_calibration_runs_use_the_standard_grader(self) -> None:
        from app.eval.datasets import EvalExample
        from app.eval.runner import resolve_rubrics, run_strategy
        from app.eval.strategies import parse_strategy

        example = EvalExample(id="e", instructions="i", draft="d", human_score=5, rubric=self.rubric)
        resolved = await resolve_rubrics([example], None, None)
        grader = FakeGrader({"thesis": 10, "support": 6}, quote="d")
        await run_strategy(parse_strategy("per_criterion"), resolved, make_client=make_client_factory(grader),
                           runs=1, essay_concurrency=1, call_concurrency=1)
        assert grader.prompts and not any("Grading style:" in p for p in grader.prompts)
