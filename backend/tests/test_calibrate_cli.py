import csv
import json
from pathlib import Path

import pytest

from scripts.calibrate import build_parser, main_async
from tests.eval_fakes import FakeGrader, make_client_factory
from tests.grading_script import RUBRIC

DRAFT = "Social media harms teen sleep. Many students scroll late at night."
GOOD = {"thesis": 10, "support": 6}
QUOTE = "Many students scroll late at night."


def make_grader(**kwargs) -> FakeGrader:
    return FakeGrader(GOOD, quote=QUOTE, **kwargs)


def write_text(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def write_dataset(path: Path, rows: int = 3, with_json_rubric: bool = True) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "instructions", "rubric_json" if with_json_rubric else "rubric",
                         "draft", "human_score", "criterion_thesis"])
        for i in range(rows):
            rubric = json.dumps(RUBRIC) if with_json_rubric else "Thesis 10, support 6"
            writer.writerow([f"e{i}", "Write.", rubric, f"{DRAFT} Essay {i}.", 12 + i, 8])
    return path


def args_for(tmp_path: Path, *extra: str, data: Path | None = None):
    data = data or write_dataset(tmp_path / "essays.csv")
    return build_parser().parse_args([
        "custom", "--data", str(data), "--out-dir", str(tmp_path / "out"),
        "--cache-dir", str(tmp_path / "cache"), "--runs", "2", *extra,
    ])


def reports(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "out").glob("*/report.md"))


async def test_full_run_writes_report_and_predictions(tmp_path: Path, capsys) -> None:
    grader = make_grader()
    code = await main_async(
        args_for(tmp_path, "--yes", "--strategies", "per_criterion", "holistic"), make_client_factory(grader)
    )
    assert code == 0
    (report_path,) = reports(tmp_path)
    report = report_path.read_text()
    assert "| per_criterion |" in report and "| holistic |" in report
    assert "## Per-criterion agreement: per_criterion" in report  # criterion_thesis column was supplied
    lines = (report_path.parent / "predictions.jsonl").read_text().splitlines()
    assert len(lines) == 6  # 3 essays x 2 strategies
    assert "Report written to" in capsys.readouterr().out


async def test_dry_run_prints_the_estimate_and_spends_nothing(tmp_path: Path, capsys) -> None:
    grader = make_grader()
    code = await main_async(
        args_for(tmp_path, "--dry-run", "--strategies", "per_criterion", "holistic"), make_client_factory(grader)
    )
    out = capsys.readouterr().out
    assert code == 0 and grader.prompts == []
    assert "per_criterion: 12" in out and "holistic: 6" in out and "total: 18" in out  # 3 essays, 2 runs
    assert reports(tmp_path) == []


async def test_declining_the_confirmation_spends_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    grader = make_grader()
    assert await main_async(args_for(tmp_path), make_client_factory(grader)) == 1
    assert grader.prompts == [] and reports(tmp_path) == []


async def test_accepting_the_confirmation_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert await main_async(args_for(tmp_path), make_client_factory(make_grader())) == 0
    assert len(reports(tmp_path)) == 1


async def test_limit_and_seed_pick_a_reproducible_sample(tmp_path: Path) -> None:
    code = await main_async(
        args_for(tmp_path, "--yes", "--limit", "2", "--seed", "1", "--strategies", "holistic"),
        make_client_factory(make_grader()),
    )
    assert code == 0
    lines = (reports(tmp_path)[0].parent / "predictions.jsonl").read_text().splitlines()
    assert len(lines) == 2


async def test_resume_skips_essays_that_are_already_graded(tmp_path: Path) -> None:
    first = make_grader()
    await main_async(args_for(tmp_path, "--yes", "--strategies", "holistic"), make_client_factory(first))
    run_dir = reports(tmp_path)[0].parent
    assert len(first.prompts) == 3 * 2  # 3 essays x 2 runs, one holistic call each

    second = make_grader()
    code = await main_async(
        args_for(tmp_path, "--yes", "--strategies", "holistic", "--resume", str(run_dir)),
        make_client_factory(second),
    )
    assert code == 0 and second.prompts == []
    assert len((run_dir / "predictions.jsonl").read_text().splitlines()) == 3  # nothing re-appended


async def test_rubric_text_is_parsed_and_cached(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "text.csv", with_json_rubric=False)
    grader = make_grader()
    code = await main_async(
        args_for(tmp_path, "--yes", "--strategies", "holistic", data=data), make_client_factory(grader)
    )
    assert code == 0
    parse_calls = [p for p in grader.prompts if "grading rubric below" in p.lower() or "Convert the grading rubric" in p]
    assert len(parse_calls) == 1  # three essays, one distinct rubric
    assert len(list((tmp_path / "cache").glob("rubric-*.json"))) == 1


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda p: write_text(p, "a,b\n1,2\n"), "missing column"),
        (lambda p: p.parent / "nope.csv", "No such file"),
    ],
)
async def test_bad_dataset_exits_with_a_message(tmp_path: Path, capsys, setup, message) -> None:
    target = setup(tmp_path / "bad.csv")
    code = await main_async(args_for(tmp_path, data=target), make_client_factory(make_grader()))
    assert code == 2 and message in capsys.readouterr().err


async def test_bad_strategy_exits_with_a_message(tmp_path: Path, capsys) -> None:
    code = await main_async(args_for(tmp_path, "--strategies", "per-criterion"), make_client_factory(make_grader()))
    assert code == 2 and "Unknown strategy mode" in capsys.readouterr().err


async def test_strategy_config_file_overrides_the_flag(tmp_path: Path) -> None:
    config = tmp_path / "s.json"
    config.write_text(json.dumps({"strategies": [{"name": "cheap", "mode": "holistic", "model": "claude-haiku-5-5"}]}))
    code = await main_async(
        args_for(tmp_path, "--yes", "--config", str(config), "--strategies", "per_criterion"),
        make_client_factory(make_grader()),
    )
    assert code == 0
    report = reports(tmp_path)[0].read_text()
    assert "| cheap | claude-haiku-5-5 |" in report and "| per_criterion |" not in report
