"""Agreement metrics between predicted and human scores. Pure Python, no numpy."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass


def quadratic_weighted_kappa(
    human: list[int], predicted: list[int], min_rating: int, max_rating: int
) -> float | None:
    """Quadratic weighted kappa: 1 is perfect agreement, 0 is chance, negative is worse.

    Returns None when it is undefined (no data, or both raters constant).
    """
    if len(human) != len(predicted):
        raise ValueError("score lists must be the same length")
    n = len(human)
    categories = max_rating - min_rating + 1
    if n == 0 or categories < 2:
        return None

    observed = [[0.0] * categories for _ in range(categories)]
    human_hist = [0.0] * categories
    pred_hist = [0.0] * categories
    for h, p in zip(human, predicted, strict=True):
        i, j = h - min_rating, p - min_rating
        if not (0 <= i < categories and 0 <= j < categories):
            raise ValueError(f"score outside [{min_rating}, {max_rating}]: human={h}, predicted={p}")
        observed[i][j] += 1
        human_hist[i] += 1
        pred_hist[j] += 1

    weighted_observed = weighted_expected = 0.0
    for i in range(categories):
        for j in range(categories):
            weight = (i - j) ** 2 / (categories - 1) ** 2
            weighted_observed += weight * observed[i][j]
            weighted_expected += weight * human_hist[i] * pred_hist[j] / n
    if weighted_expected == 0:
        return None
    return 1.0 - weighted_observed / weighted_expected


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return cov / math.sqrt(var_x * var_y)


@dataclass
class CriterionPrediction:
    name: str
    max_points: float
    predicted: float          # median points across runs
    predicted_min: float
    predicted_max: float
    predicted_rank: int       # which rubric level the median is closest to (0 = lowest)
    human: float | None = None
    human_rank: int | None = None


@dataclass
class Prediction:
    """One essay graded by one strategy. Totals are on the human score scale."""

    strategy: str
    example_id: str
    human_score: float
    min_score: float
    max_score: float
    predicted: float | None = None
    predicted_min: float | None = None
    predicted_max: float | None = None
    criteria: dict[str, CriterionPrediction] | None = None
    evidence_total: int = 0
    evidence_verified: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.predicted is not None


@dataclass
class CriterionAgreement:
    name: str
    n: int
    mae: float
    exact: float       # share of essays where the level matches the human's
    adjacent: float    # share within one level


@dataclass
class Summary:
    n: int
    failed: int
    mae: float | None
    mae_pct: float | None       # MAE as a percentage of the scale's maximum
    bias: float | None          # mean (predicted - human); positive = too generous
    coverage: float | None      # share of essays whose human score is inside the predicted range
    mean_range_width: float | None
    qwk: float | None
    pearson: float | None
    evidence_verified_rate: float | None
    criteria: dict[str, CriterionAgreement]
    worst: list[Prediction]


def summarize(predictions: list[Prediction], worst_n: int = 5) -> Summary:
    ok = [p for p in predictions if p.ok]
    failed = len(predictions) - len(ok)
    if not ok:
        return Summary(0, failed, None, None, None, None, None, None, None, None, {}, [])

    errors = [p.predicted - p.human_score for p in ok]  # type: ignore[operator]
    mae = sum(abs(e) for e in errors) / len(ok)
    scale_max = sum(p.max_score for p in ok) / len(ok)
    covered = [
        p.predicted_min - 1e-9 <= p.human_score <= p.predicted_max + 1e-9  # type: ignore[operator]
        for p in ok
    ]
    widths = [p.predicted_max - p.predicted_min for p in ok]  # type: ignore[operator]

    # QWK needs one shared integer scale.
    scales = {(p.min_score, p.max_score) for p in ok}
    qwk = None
    if len(scales) == 1:
        low, high = round(next(iter(scales))[0]), round(next(iter(scales))[1])
        qwk = quadratic_weighted_kappa(
            [min(max(round(p.human_score), low), high) for p in ok],
            [min(max(round(p.predicted), low), high) for p in ok],  # type: ignore[arg-type]
            low, high,
        )

    evidence_total = sum(p.evidence_total for p in ok)
    return Summary(
        n=len(ok),
        failed=failed,
        mae=mae,
        mae_pct=100 * mae / scale_max if scale_max else None,
        bias=sum(errors) / len(ok),
        coverage=sum(covered) / len(ok),
        mean_range_width=sum(widths) / len(ok),
        qwk=qwk,
        pearson=pearson([p.human_score for p in ok], [p.predicted for p in ok]),  # type: ignore[misc]
        evidence_verified_rate=(
            sum(p.evidence_verified for p in ok) / evidence_total if evidence_total else None
        ),
        criteria=_criterion_agreement(ok),
        worst=sorted(ok, key=lambda p: -abs(p.predicted - p.human_score))[:worst_n],  # type: ignore[operator]
    )


def _criterion_agreement(predictions: list[Prediction]) -> dict[str, CriterionAgreement]:
    grouped: dict[str, list[CriterionPrediction]] = defaultdict(list)
    for prediction in predictions:
        for criterion_id, item in (prediction.criteria or {}).items():
            if item.human is not None and item.human_rank is not None:
                grouped[criterion_id].append(item)
    result = {}
    for criterion_id, items in grouped.items():
        gaps = [abs(i.predicted_rank - i.human_rank) for i in items]  # type: ignore[operator]
        result[criterion_id] = CriterionAgreement(
            name=items[0].name,
            n=len(items),
            mae=sum(abs(i.predicted - i.human) for i in items) / len(items),  # type: ignore[operator]
            exact=sum(g == 0 for g in gaps) / len(items),
            adjacent=sum(g <= 1 for g in gaps) / len(items),
        )
    return result
