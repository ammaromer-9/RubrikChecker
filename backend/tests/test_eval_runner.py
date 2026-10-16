import json
from pathlib import Path

import pytest

from app.eval.datasets import EvalExample
from app.eval.metrics import Prediction
from app.eval.runner import (
    estimate_calls,
    load_done,
    prediction_from_json,
    prediction_to_json,
    resolve_rubrics,
    run_strategy,
)
from app.eval.strategies import StrategySpec, parse_strategy
from app.schemas.rubric import Rubric
from app.services.llm_client import LLMClient, LLMError
from app.services.llm_testing import FakeLLMProvider, InMemoryCallRecorder
from tests.eval_fakes import FakeGrader, make_client_factory
from tests.grading_script import RUBRIC

DRAFT = "Social media harms teen sleep. Many students scroll late at night."
QUOTE = "Many students scroll late at night."
GOOD = {"thesis": 10, "support": 6}
MIDDLE = {"thesis": 5, "support": 3}


def example(example_id="e1", human=12.0, **kwargs) -> EvalExample:
    base = {
        "instructions": "Write.", "draft": DRAFT, "human_score": human,
        "rubric": Rubric.model_validate(RUBRIC),
    }
    return EvalExample(id=example_id, **{**base, **kwargs})


async def resolved(*examples: EvalExample):
    return await resolve_rubrics(list(examples), None, None)


async def run(spec: StrategySpec, items, grader: FakeGrader, runs: int = 3, **kwargs):
    return await run_strategy(
        spec, items, make_client=make_client_factory(grader), runs=runs,
        essay_concurrency=2, call_concurrency=4, **kwargs,
    )


async def test_per_criterion_prediction_and_usage() -> None:
    items = await resolved(example(human=14, criterion_scores={"thesis": 10, "Evidence & Support": 3}))
    grader = FakeGrader(MIDDLE, quote=QUOTE)
    result = await run(parse_strategy("per_criterion"), items, grader)

    (p,) = result.predictions
    assert p.ok and (p.predicted, p.predicted_min, p.predicted_max) == (8, 8, 8)
    assert p.human_score == 14 and p.max_score == 16
    assert {k: c.predicted for k, c in p.criteria.items()} == {"thesis": 5, "support": 3}
    # 2 criteria x 3 runs, one verified quote each
    assert (p.evidence_total, p.evidence_verified) == (6, 6)
    assert result.usage.calls == 6 and result.usage.input_tokens == 60 and result.usage.failed_calls == 0

    # Human per-criterion scores are matched by id or by name and turned into level ranks.
    thesis, support = p.criteria["thesis"], p.criteria["support"]
    assert (thesis.human, thesis.human_rank, thesis.predicted_rank) == (10, 2, 1)
    assert (support.human, support.human_rank, support.predicted_rank) == (3, 1, 1)


async def test_made_up_quotes_lower_the_verified_rate() -> None:
    items = await resolved(example())
    result = await run(parse_strategy("per_criterion"), items, FakeGrader(GOOD, quote=QUOTE, bad_quote=True))
    p = result.predictions[0]
    assert p.evidence_total == 6 and p.evidence_verified == 0


async def test_no_evidence_strategy_uses_the_no_evidence_prompt() -> None:
    items = await resolved(example())
    grader = FakeGrader(GOOD, quote=QUOTE)
    result = await run(parse_strategy("per_criterion:no_evidence"), items, grader)
    assert result.predictions[0].evidence_total == 0
    assert all('"evidence"' not in prompt for prompt in grader.prompts)

    with_evidence = FakeGrader(GOOD, quote=QUOTE)
    await run(parse_strategy("per_criterion"), items, with_evidence)
    assert all('"evidence"' in prompt for prompt in with_evidence.prompts)


async def test_evidence_strategy_insists_on_a_quote() -> None:
    items = await resolved(example())
    grader = FakeGrader(GOOD, quote=QUOTE, omit_evidence=True)  # model gives no quotes at all
    result = await run(parse_strategy("per_criterion"), items, grader, runs=1)
    # Every criterion fails validation twice (original + retry), so the essay fails.
    failed = result.predictions[0]
    assert not failed.ok and "evidence" in failed.error


async def test_holistic_uses_one_call_per_run() -> None:
    items = await resolved(example(criterion_scores={"thesis": 10}))
    grader = FakeGrader(MIDDLE, quote=QUOTE)
    result = await run(parse_strategy("holistic"), items, grader, runs=3)
    p = result.predictions[0]
    assert result.usage.calls == 3  # per_criterion would need 6
    assert p.predicted == 8 and p.criteria["thesis"].human_rank == 2
    assert p.evidence_total == 6 and p.evidence_verified == 6  # 2 criteria x 3 runs
    assert all("Grade every criterion in one pass" in prompt for prompt in grader.prompts)


async def test_run_disagreement_becomes_a_range() -> None:
    per_run = [GOOD, MIDDLE, MIDDLE]  # one holistic call per run: totals 16, 8, 8
    calls = {"n": 0}

    def points(prompt: str) -> dict[str, int]:
        calls["n"] += 1
        return per_run[calls["n"] - 1]

    items = await resolved(example(human=8))
    result = await run(parse_strategy("holistic"), items, FakeGrader(points, quote=QUOTE), runs=3)
    p = result.predictions[0]
    assert (p.predicted, p.predicted_min, p.predicted_max) == (8, 8, 16)
    assert p.criteria["thesis"].predicted_min == 5 and p.criteria["thesis"].predicted_max == 10


async def test_predictions_are_scaled_and_clamped_to_the_human_scale() -> None:
    # Rubric totals 16 but the human scale is 2-12 (like ASAP set 1).
    items = await resolved(
        example("high", human=11, max_score=12, min_score=2),
        example("low", human=3, max_score=12, min_score=2),
    )
    high = await run(parse_strategy("holistic"), items[:1], FakeGrader(GOOD, quote=QUOTE), runs=1)
    low = await run(parse_strategy("holistic"), items[1:], FakeGrader({"thesis": 0, "support": 0}, quote=QUOTE), runs=1)
    assert high.predictions[0].predicted == 12      # 16 * 12/16
    assert low.predictions[0].predicted == 2        # 0 clamped up to the minimum a human could give
    middle = await run(parse_strategy("holistic"), items[:1], FakeGrader(MIDDLE, quote=QUOTE), runs=1)
    assert middle.predictions[0].predicted == 6     # 8 * 12/16


async def test_a_failing_essay_is_recorded_and_does_not_stop_the_run() -> None:
    items = await resolved(example("ok"), example("bad", draft="BOOM"))

    def points(prompt: str) -> dict[str, int]:
        if "BOOM" in prompt:
            raise LLMError("model unavailable")
        return GOOD

    result = await run(parse_strategy("holistic"), items, FakeGrader(points, quote=QUOTE), runs=1)
    by_id = {p.example_id: p for p in result.predictions}
    assert by_id["ok"].ok
    assert not by_id["bad"].ok and "model unavailable" in by_id["bad"].error
    assert result.usage.failed_calls == 1


async def test_already_done_essays_are_not_graded_again() -> None:
    items = await resolved(example("a"), example("b"))
    first = FakeGrader(GOOD, quote=QUOTE)
    result = await run(parse_strategy("holistic"), items[:1], first, runs=1)
    done = {p.example_id: p for p in result.predictions}

    second = FakeGrader(GOOD, quote=QUOTE)
    saved: list[Prediction] = []
    resumed = await run(parse_strategy("holistic"), items, second, runs=1, done=done, on_prediction=saved.append)
    assert [p.example_id for p in resumed.predictions] == ["a", "b"]
    assert len(second.prompts) == 1 and [p.example_id for p in saved] == ["b"]


async def test_each_strategy_can_use_its_own_model() -> None:
    providers: list[FakeLLMProvider] = []
    items = await resolved(example())
    await run_strategy(
        parse_strategy("holistic@claude-haiku-5-5"), items,
        make_client=make_client_factory(FakeGrader(GOOD), providers), runs=1,
        essay_concurrency=1, call_concurrency=1,
    )
    assert providers[0].model == "claude-haiku-5-5"


async def test_estimate_calls() -> None:
    items = await resolved(example("a"), example("b"))
    specs = [parse_strategy("per_criterion"), parse_strategy("holistic")]
    assert estimate_calls(specs, items, runs=3) == {"per_criterion": 2 * 2 * 3, "holistic": 2 * 3}


async def test_predictions_survive_a_save_and_load(tmp_path: Path) -> None:
    items = await resolved(example("a"), example("b", draft="BOOM"))

    def points(prompt: str) -> dict[str, int]:
        if "BOOM" in prompt:
            raise LLMError("nope")
        return GOOD

    result = await run(parse_strategy("holistic"), items, FakeGrader(points, quote=QUOTE), runs=1)
    path = tmp_path / "predictions.jsonl"
    path.write_text("\n".join(prediction_to_json(p) for p in result.predictions) + "\n")

    restored = prediction_from_json(path.read_text().splitlines()[0])
    assert restored == result.predictions[0]
    done = load_done(path)
    assert list(done["holistic"]) == ["a"]  # the failed essay will be retried on resume


class TestResolveRubrics:
    def text_example(self, example_id: str, rubric_text: str = "Thesis: 10. Support: 6.", **kwargs) -> EvalExample:
        return EvalExample(id=example_id, instructions="W", draft="D", human_score=5, rubric_text=rubric_text, **kwargs)

    def client(self, grader: FakeGrader) -> LLMClient:
        return make_client_factory(grader)(None, InMemoryCallRecorder())

    async def test_each_distinct_rubric_text_is_parsed_once(self) -> None:
        grader = FakeGrader(GOOD)
        items = [self.text_example("a"), self.text_example("b"), self.text_example("c", "Different rubric")]
        out = await resolve_rubrics(items, self.client(grader), None)
        assert len(grader.prompts) == 2
        assert all(r.scale_max == 16 for r in out)

    async def test_parsed_rubrics_are_cached_on_disk(self, tmp_path: Path) -> None:
        first = FakeGrader(GOOD)
        await resolve_rubrics([self.text_example("a")], self.client(first), tmp_path)
        assert len(first.prompts) == 1 and len(list(tmp_path.glob("rubric-*.json"))) == 1

        second = FakeGrader(GOOD)
        out = await resolve_rubrics([self.text_example("a")], self.client(second), tmp_path)
        assert second.prompts == [] and len(out[0].rubric.criteria) == 2

    async def test_structured_rubrics_need_no_llm(self) -> None:
        out = await resolve_rubrics([example()], None, None)
        assert out[0].rubric.total_points == 16

    async def test_missing_client_for_text_rubric_is_a_clear_error(self) -> None:
        with pytest.raises(RuntimeError, match="LLM client"):
            await resolve_rubrics([self.text_example("a")], None, None)

    async def test_criterion_columns_match_by_id_or_name_and_unmatched_ones_warn(self) -> None:
        item = example(criterion_scores={"thesis": 8, "evidence_support": 4, "typo": 1})
        (out,) = await resolve_rubrics([item], None, None)
        assert out.criterion_human == {"thesis": 8, "support": 4}
        assert len(out.warnings) == 1 and "criterion_typo" in out.warnings[0]

    async def test_scale_defaults_to_the_rubric_total(self) -> None:
        (out,) = await resolve_rubrics([example()], None, None)
        assert (out.scale_min, out.scale_max) == (0, 16)
        (custom,) = await resolve_rubrics([example(max_score=100)], None, None)
        assert custom.scale_max == 100


def test_spec_json_roundtrip_is_plain() -> None:
    assert json.loads(prediction_to_json(Prediction(
        strategy="s", example_id="e", human_score=1, min_score=0, max_score=2, error="x"))
    )["error"] == "x"
