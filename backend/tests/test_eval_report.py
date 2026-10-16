from datetime import datetime

from app.eval.metrics import CriterionPrediction, Prediction
from app.eval.report import ReportMeta, render_report
from app.eval.runner import StrategyResult, Usage
from app.eval.strategies import parse_strategy


def prediction(strategy, example_id, human, predicted, low, high, *, criteria=None, verified=(0, 0), error=None):
    return Prediction(
        strategy=strategy, example_id=example_id, human_score=human, min_score=0, max_score=10,
        predicted=None if error else predicted, predicted_min=None if error else low,
        predicted_max=None if error else high, criteria=criteria, evidence_total=verified[0],
        evidence_verified=verified[1], error=error,
    )


def result(name, predictions, model_calls=10):
    return StrategyResult(parse_strategy(name), predictions, Usage(model_calls, 0, 1000, 200, 150.0))


META = ReportMeta(dataset="essays.csv", examples=3, runs=3, default_model="claude-sonnet-5-5",
                  generated_at=datetime(2026, 10, 15, 12, 30))


def test_comparison_table_has_one_row_per_strategy_with_metrics() -> None:
    a = result("per_criterion", [
        prediction("per_criterion", "e1", 8, 7, 6, 9, verified=(4, 3)),
        prediction("per_criterion", "e2", 5, 6, 5, 7, verified=(4, 4)),
    ])
    b = result("holistic@claude-haiku-5-5", [prediction("holistic@claude-haiku-5-5", "e1", 8, 9, 9, 9)])
    report = render_report(META, [a, b])

    assert report.startswith("# Calibration report")
    assert "- **Dataset:** essays.csv (3 essays)" in report
    rows = {line.split("|")[1].strip(): line for line in report.splitlines() if line.startswith("| ") and "---" not in line}
    row = rows["per_criterion"]
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[1] == "claude-sonnet-5-5"                    # default model shown
    assert cells[2:4] == ["2", "0"]                            # graded, failed
    assert cells[4] == "1.00" and cells[5] == "10.0%"          # MAE 1.0 of 10 points
    assert cells[6] == "+0.00" and cells[7] == "100%"          # bias, coverage
    assert cells[11] == "88%"                                  # 7 of 8 quotes verified
    assert cells[12] == "500 / 100"                            # tokens per essay
    assert rows["holistic@claude-haiku-5-5"].split("|")[2].strip() == "claude-haiku-5-5"


def test_unavailable_metrics_are_marked_na_not_zero() -> None:
    report = render_report(META, [result("holistic", [prediction("holistic", "e1", 5, 5, 5, 5)])])
    row = next(line for line in report.splitlines() if line.startswith("| holistic"))
    assert "n/a" in row  # Pearson, quotes verified: undefined for one essay / no quotes


def test_failed_essays_are_listed() -> None:
    report = render_report(META, [result("holistic", [
        prediction("holistic", "e1", 5, 5, 5, 5), prediction("holistic", "e2", 5, 0, 0, 0, error="model unavailable"),
    ])])
    assert "## Failed essays" in report and "holistic / e2: model unavailable" in report


def test_per_criterion_and_miss_sections() -> None:
    crit = {"t": CriterionPrediction("Thesis", 10, 8, 8, 8, 2, human=5, human_rank=1)}
    report = render_report(META, [result("per_criterion", [
        prediction("per_criterion", "e1", 5, 9, 8, 10, criteria=crit)])])
    assert "## Per-criterion agreement: per_criterion" in report
    assert "| Thesis | 1 | 3.00 | 0% | 100% |" in report
    assert "## Largest misses: per_criterion" in report and "| e1 | 5 | 9.0 | 8.0–10.0 |" in report


def test_warnings_section_only_when_present() -> None:
    plain = render_report(META, [result("holistic", [prediction("holistic", "e1", 5, 5, 5, 5)])])
    assert "## Warnings" not in plain
    META_WARN = ReportMeta(**{**META.__dict__, "warnings": ["row3: column 'criterion_x' matches no criterion"]})
    assert "## Warnings\n\n- row3" in render_report(META_WARN, [result("holistic", [prediction("holistic", "e1", 5, 5, 5, 5)])])
