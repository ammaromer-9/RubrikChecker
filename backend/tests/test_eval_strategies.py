import json
from pathlib import Path

import pytest

from app.eval.holistic import holistic_schema_for
from app.eval.strategies import StrategyError, StrategySpec, load_strategy_config, parse_strategy
from app.schemas.rubric import Rubric
from tests.grading_script import RUBRIC


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("per_criterion", StrategySpec("per_criterion", "per_criterion", True, None)),
        ("holistic", StrategySpec("holistic", "holistic", True, None)),
        ("per_criterion:no_evidence", StrategySpec("per_criterion:no_evidence", "per_criterion", False, None)),
        ("holistic@claude-haiku-5-5", StrategySpec("holistic@claude-haiku-5-5", "holistic", True, "claude-haiku-5-5")),
        ("holistic:no_evidence@m", StrategySpec("holistic:no_evidence@m", "holistic", False, "m")),
    ],
)
def test_parse_strategy(text: str, expected: StrategySpec) -> None:
    assert parse_strategy(text) == expected


@pytest.mark.parametrize("text", ["per-criterion", "holistic:fast", "holistic@", "", "no_evidence"])
def test_parse_strategy_rejects_typos(text: str) -> None:
    with pytest.raises(StrategyError):
        parse_strategy(text)


def test_config_file(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"strategies": [
        "holistic",
        {"name": "cheap", "mode": "per_criterion", "evidence": False, "model": "claude-haiku-5-5"},
    ]}))
    holistic, cheap = load_strategy_config(path)
    assert holistic.mode == "holistic"
    assert cheap == StrategySpec("cheap", "per_criterion", False, "claude-haiku-5-5")


@pytest.mark.parametrize(
    "content",
    ["not json", "{}", '{"strategies": []}', '{"strategies": [5]}', '{"strategies": ["holistic", "holistic"]}'],
)
def test_bad_config_files(tmp_path: Path, content: str) -> None:
    path = tmp_path / "s.json"
    path.write_text(content)
    with pytest.raises(StrategyError):
        load_strategy_config(path)


class TestHolisticSchema:
    rubric = Rubric.model_validate(RUBRIC)

    def valid(self, evidence: bool = True) -> dict:
        item = {"reasoning": "r", "level_label": "Excellent"}
        if evidence:
            item["evidence"] = [{"quote": "q", "supports": "met"}]
        return {"criteria": {"thesis": item, "support": {**item, "level_label": "Strong"}}}

    def test_valid_reply(self) -> None:
        parsed = holistic_schema_for(self.rubric, True).model_validate(self.valid())
        assert parsed.criteria.thesis.level_label == "Excellent"  # type: ignore[attr-defined]

    def test_each_criterion_has_its_own_labels(self) -> None:
        data = self.valid()
        data["criteria"]["support"]["level_label"] = "Excellent"  # a thesis label, not a support label
        with pytest.raises(ValueError, match="level_label"):
            holistic_schema_for(self.rubric, True).model_validate(data)

    def test_missing_criterion_is_rejected(self) -> None:
        data = self.valid()
        del data["criteria"]["support"]
        with pytest.raises(ValueError, match="support"):
            holistic_schema_for(self.rubric, False).model_validate(data)

    def test_evidence_is_required_only_when_enforced(self) -> None:
        no_evidence = self.valid(evidence=False)
        holistic_schema_for(self.rubric, False).model_validate(no_evidence)
        with pytest.raises(ValueError, match="evidence"):
            holistic_schema_for(self.rubric, True).model_validate(no_evidence)

    def test_criterion_ids_with_hyphens_work(self) -> None:
        rubric = Rubric.model_validate({"criteria": [{
            "id": "use-of-evidence", "name": "E", "max_points": 5, "levels": [{"label": "Good", "points": 5}],
        }]})
        schema = holistic_schema_for(rubric, False)
        parsed = schema.model_validate({"criteria": {"use-of-evidence": {"reasoning": "r", "level_label": "Good"}}})
        assert getattr(parsed.criteria, "use-of-evidence").level_label == "Good"  # type: ignore[attr-defined]
