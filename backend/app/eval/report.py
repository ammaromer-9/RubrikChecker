"""Markdown report comparing grading strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.eval.metrics import Summary, summarize
from app.eval.runner import StrategyResult


@dataclass
class ReportMeta:
    dataset: str
    examples: int
    runs: int
    default_model: str
    generated_at: datetime
    warnings: list[str] = field(default_factory=list)


def _num(value: float | None, digits: int = 2, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{suffix}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.0f}%"


def render_report(meta: ReportMeta, results: list[StrategyResult]) -> str:
    summaries: list[tuple[StrategyResult, Summary]] = [(r, summarize(r.predictions)) for r in results]
    lines = [
        "# Calibration report",
        "",
        f"- **Dataset:** {meta.dataset} ({meta.examples} essays)",
        f"- **Grading runs per essay:** {meta.runs}",
        f"- **Default model:** {meta.default_model}",
        f"- **Generated:** {meta.generated_at:%Y-%m-%d %H:%M}",
        "",
        "## Strategy comparison",
        "",
        (
            "| Strategy | Model | Graded | Failed | MAE (pts) | MAE (% of scale) | Bias | Coverage | "
            "Range width | QWK | Pearson r | Quotes verified | Tokens/essay (in / out) |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result, s in summaries:
        graded = max(len(result.predictions), 1)
        tokens = f"{result.usage.input_tokens / graded:,.0f} / {result.usage.output_tokens / graded:,.0f}"
        lines.append(
            f"| {result.spec.name} | {result.spec.model or meta.default_model} | {s.n} | {s.failed} | "
            f"{_num(s.mae)} | {_num(s.mae_pct, 1, '%')} | {_signed(s.bias)} | {_pct(s.coverage)} | "
            f"{_num(s.mean_range_width)} | {_num(s.qwk, 3)} | {_num(s.pearson, 3)} | "
            f"{_pct(s.evidence_verified_rate)} | {tokens} |"
        )
    lines += [
        "",
        "How to read this:",
        "",
        "- **MAE**: average distance between predicted and human score; lower is better.",
        "- **Bias**: average predicted minus human score. Positive means the grader is too generous.",
        (
            "- **Coverage**: how often the human score fell inside the predicted range. "
            "Compare it with **range width**: a very wide range covers easily but says little."
        ),
        (
            "- **QWK** (quadratic weighted kappa): 1 is perfect agreement, 0 is chance. "
            "Shown only when every essay shares one integer score scale."
        ),
        (
            "- **Quotes verified**: share of evidence quotes that really appear in the essay "
            "(n/a for strategies that do not ask for quotes). Anything below 100% means the model "
            "made up text."
        ),
        "- Token counts only cover calls made in this run (resumed essays are not recounted).",
    ]

    for result, s in summaries:
        if s.criteria:
            lines += ["", f"## Per-criterion agreement: {result.spec.name}", "",
                      "| Criterion | Essays | MAE (pts) | Same level | Within one level |",
                      "|---|---:|---:|---:|---:|"]
            for agreement in s.criteria.values():
                lines.append(
                    f"| {agreement.name} | {agreement.n} | {_num(agreement.mae)} | "
                    f"{_pct(agreement.exact)} | {_pct(agreement.adjacent)} |"
                )

    for result, s in summaries:
        if s.worst:
            lines += ["", f"## Largest misses: {result.spec.name}", "",
                      "| Essay | Human | Predicted | Range |", "|---|---:|---:|---|"]
            for p in s.worst:
                lines.append(
                    f"| {p.example_id} | {p.human_score:g} | {_num(p.predicted, 1)} | "
                    f"{_num(p.predicted_min, 1)}–{_num(p.predicted_max, 1)} |"
                )

    failures = [p for r, _ in summaries for p in r.predictions if not p.ok]
    if failures:
        lines += ["", "## Failed essays", ""]
        lines += [f"- {p.strategy} / {p.example_id}: {p.error}" for p in failures[:20]]
        if len(failures) > 20:
            lines.append(f"- ...and {len(failures) - 20} more")
    if meta.warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in meta.warnings]
    return "\n".join(lines) + "\n"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"
