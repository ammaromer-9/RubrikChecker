"""Combine several grading runs into one score, a range, and an uncertainty flag."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.schemas.rubric import Criterion


@dataclass(frozen=True)
class CriterionAggregate:
    median: float
    minimum: float
    maximum: float
    uncertain: bool
    # Index of the run whose reasoning and evidence are shown to the student.
    representative: int


def level_rank(criterion: Criterion, points: float) -> int:
    """Position of `points` among the criterion's distinct level scores, lowest first."""
    scores = sorted({level.points for level in criterion.levels})
    return min(range(len(scores)), key=lambda i: abs(scores[i] - points))


def aggregate_criterion(criterion: Criterion, run_points: list[float]) -> CriterionAggregate:
    """Median, min-max range, and `uncertain` when runs disagree by more than one level."""
    if not run_points:
        raise ValueError("cannot aggregate zero runs")
    median = statistics.median(run_points)
    ranks = [level_rank(criterion, p) for p in run_points]
    representative = min(range(len(run_points)), key=lambda i: abs(run_points[i] - median))
    return CriterionAggregate(
        median=median,
        minimum=min(run_points),
        maximum=max(run_points),
        uncertain=max(ranks) - min(ranks) > 1,
        representative=representative,
    )


@dataclass(frozen=True)
class OverallAggregate:
    median: float
    minimum: float
    maximum: float


def aggregate_overall(criteria: list[CriterionAggregate]) -> OverallAggregate:
    """Overall score is the sum of per-criterion medians.

    The range sums the per-criterion minimums and maximums. That is deliberately
    conservative (it assumes every criterion hits its low or high end together),
    so the true score is rarely outside it.
    """
    return OverallAggregate(
        median=sum(c.median for c in criteria),
        minimum=sum(c.minimum for c in criteria),
        maximum=sum(c.maximum for c in criteria),
    )
