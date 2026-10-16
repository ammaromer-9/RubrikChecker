import csv
import json
from pathlib import Path

import pytest

from app.eval.datasets import (
    ASAP_SCORE_RANGES,
    DatasetError,
    load_asap,
    load_custom_csv,
    sample_examples,
)
from tests.grading_script import RUBRIC


def write_csv(path: Path, header: list[str], rows: list[list[str]], delimiter: str = ",", encoding: str = "utf-8") -> Path:
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(header)
        writer.writerows(rows)
    return path


HEADER = ["id", "instructions", "rubric", "draft", "human_score"]


class TestCustomCsv:
    def test_loads_rows(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "e.csv", HEADER, [
            ["e1", "Write.", "Thesis: 10", "My draft\nwith lines", "7.5"],
            ["", "Write.", "Thesis: 10", "Another", "3"],
        ])
        first, second = load_custom_csv(path)
        assert (first.id, first.human_score, first.draft) == ("e1", 7.5, "My draft\nwith lines")
        assert first.rubric_text == "Thesis: 10" and first.rubric is None
        assert first.max_score is None
        assert second.id == "row3"  # header is row 1

    def test_structured_rubric_and_scale_and_criterion_columns(self, tmp_path: Path) -> None:
        path = write_csv(
            tmp_path / "e.csv",
            ["instructions", "rubric_json", "draft", "human_score", "max_score", "criterion_thesis", "criterion_support"],
            [["Write.", json.dumps(RUBRIC), "Draft", "12", "16", "10", ""]],
        )
        (example,) = load_custom_csv(path)
        assert example.rubric is not None and len(example.rubric.criteria) == 2
        assert example.max_score == 16
        assert example.criterion_scores == {"thesis": 10}  # blank cells are skipped

    @pytest.mark.parametrize(
        ("header", "rows", "message"),
        [
            (["instructions", "draft", "rubric"], [["a", "b", "c"]], "missing column.*human_score"),
            (["instructions", "draft", "human_score"], [["a", "b", "1"]], "'rubric' or 'rubric_json'"),
            (HEADER, [["x", "Write.", "R", "Draft", "high"]], r"Row 2: 'human_score' must be a number, got 'high'"),
            (HEADER, [["x", "Write.", "R", "   ", "5"]], r"Row 2: 'draft' is empty"),
            (HEADER, [["x", "", "R", "Draft", "5"]], r"Row 2: 'instructions' is empty"),
            (HEADER, [["x", "W", "", "Draft", "5"]], r"Row 2: needs 'rubric' text"),
            (HEADER, [], "no data rows"),
        ],
    )
    def test_errors_name_the_problem(self, tmp_path: Path, header, rows, message) -> None:
        with pytest.raises(DatasetError, match=message):
            load_custom_csv(write_csv(tmp_path / "e.csv", header, rows))

    def test_invalid_rubric_json_is_reported_with_the_row(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "e.csv", ["instructions", "rubric_json", "draft", "human_score"],
                         [["W", '{"criteria": []}', "D", "5"]])
        with pytest.raises(DatasetError, match="Row 2: 'rubric_json' is not a valid rubric"):
            load_custom_csv(path)

    def test_utf8_bom_is_handled(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "e.csv", HEADER, [["e", "W", "R", "café", "1"]], encoding="utf-8-sig")
        assert load_custom_csv(path)[0].draft == "café"


ASAP_HEADER = ["essay_id", "essay_set", "essay", "rater1_domain1", "domain1_score"]


class TestAsap:
    def make(self, tmp_path: Path, name: str = "training_set_rel3.tsv", **kwargs) -> Path:
        return write_csv(
            tmp_path / name, ASAP_HEADER,
            [
                ["1", "1", "Dear local newspaper, @CAPS1 café", "4", "8"],
                ["2", "2", "Other set essay", "3", "4"],
                ["3", "1", "Unscored essay", "", ""],
                ["4", "1", "Another set one essay", "5", "10"],
            ],
            delimiter="\t" if name.endswith(".tsv") else ",", **kwargs,
        )

    def load(self, path: Path, **kwargs):
        return load_asap(path, essay_set=kwargs.pop("essay_set", 1), instructions="Prompt", rubric_text="Rubric", **kwargs)

    def test_filters_by_set_and_skips_unscored_essays(self, tmp_path: Path) -> None:
        examples = self.load(self.make(tmp_path))
        assert [e.id for e in examples] == ["asap1-1", "asap1-4"]
        first = examples[0]
        assert (first.human_score, first.min_score, first.max_score) == (8, 2, 12)
        assert first.instructions == "Prompt" and first.rubric_text == "Rubric"

    def test_reads_latin1_files_like_the_real_dataset(self, tmp_path: Path) -> None:
        path = self.make(tmp_path, encoding="latin-1")
        assert "café" in self.load(path)[0].draft

    def test_csv_variant_and_score_range_override(self, tmp_path: Path) -> None:
        examples = self.load(self.make(tmp_path, "asap.csv"), score_range=(0, 20))
        assert (examples[0].min_score, examples[0].max_score) == (0, 20)

    def test_unknown_set_needs_a_score_range(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="--score-range"):
            self.load(self.make(tmp_path), essay_set=99)

    def test_set_without_essays(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="no scored essays found for essay set 5"):
            self.load(self.make(tmp_path), essay_set=5)

    def test_rejects_files_that_are_not_asap(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "x.tsv", ["a", "b"], [["1", "2"]], delimiter="\t")
        with pytest.raises(DatasetError, match="not an ASAP file"):
            self.load(path)

    def test_known_score_ranges(self) -> None:
        assert set(ASAP_SCORE_RANGES) == set(range(1, 9))


def test_sample_examples() -> None:
    from app.eval.datasets import EvalExample

    examples = [EvalExample(id=str(i), instructions="i", draft="d", human_score=1, rubric_text="r") for i in range(20)]
    assert sample_examples(examples, None, None) is examples
    assert [e.id for e in sample_examples(examples, 3, None)] == ["0", "1", "2"]
    a, b = sample_examples(examples, 5, seed=1), sample_examples(examples, 5, seed=1)
    assert [e.id for e in a] == [e.id for e in b] and len(a) == 5
    assert [e.id for e in a] != [e.id for e in sample_examples(examples, 5, seed=2)]
    assert sample_examples(examples, 50, seed=1) is examples
