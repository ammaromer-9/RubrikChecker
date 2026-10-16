import pytest

from app.eval.metrics import (
    CriterionPrediction,
    Prediction,
    pearson,
    quadratic_weighted_kappa,
    summarize,
)


class TestQuadraticWeightedKappa:
    def test_perfect_agreement_is_one(self) -> None:
        assert quadratic_weighted_kappa([1, 2, 3, 4], [1, 2, 3, 4], 1, 4) == pytest.approx(1.0)

    def test_total_disagreement_is_minus_one(self) -> None:
        assert quadratic_weighted_kappa([0, 1, 2], [2, 1, 0], 0, 2) == pytest.approx(-1.0)

    def test_near_misses_hurt_less_than_far_misses(self) -> None:
        human = [1, 2, 3, 4, 1, 2, 3, 4]
        near = quadratic_weighted_kappa(human, [2, 2, 3, 3, 1, 3, 3, 4], 1, 4)
        far = quadratic_weighted_kappa(human, [4, 2, 3, 1, 1, 4, 3, 4], 1, 4)
        assert far < near < 1
        assert near > 0.5

    def test_known_value(self) -> None:
        # Worked by hand. Disagreement weights are (i-j)^2/4 for 3 categories.
        # Observed: (0,1) and (1,2) each once -> 0.25 + 0.25 = 0.5.
        # Expected from the marginals (human 2,2,2; predicted 1,2,3 over 6 essays) = 2.0.
        # kappa = 1 - 0.5 / 2.0 = 0.75
        assert quadratic_weighted_kappa([0, 0, 1, 1, 2, 2], [0, 1, 1, 2, 2, 2], 0, 2) == pytest.approx(0.75)

    def test_undefined_cases_return_none(self) -> None:
        assert quadratic_weighted_kappa([], [], 0, 3) is None
        assert quadratic_weighted_kappa([2, 2], [2, 2], 0, 3) is None  # both constant
        assert quadratic_weighted_kappa([1], [1], 1, 1) is None  # one category

    def test_rejects_bad_input(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            quadratic_weighted_kappa([1], [1, 2], 0, 3)
        with pytest.raises(ValueError, match="outside"):
            quadratic_weighted_kappa([5], [1], 0, 3)


def test_pearson() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert pearson([1], [1]) is None


def pred(example_id, human, predicted, low=None, high=None, scale=(0, 10), **kwargs):
    return Prediction(
        strategy="s", example_id=example_id, human_score=human, min_score=scale[0], max_score=scale[1],
        predicted=predicted, predicted_min=predicted if low is None else low,
        predicted_max=predicted if high is None else high, **kwargs,
    )


def test_summary_core_metrics() -> None:
    summary = summarize([
        pred("a", human=8, predicted=6, low=5, high=9),    # error -2, covered
        pred("b", human=4, predicted=5, low=5, high=6),    # error +1, not covered
        pred("c", human=7, predicted=7, low=6, high=8),    # error 0, covered
    ])
    assert summary.n == 3 and summary.failed == 0
    assert summary.mae == pytest.approx(1.0)
    assert summary.mae_pct == pytest.approx(10.0)  # 1 / scale max 10
    assert summary.bias == pytest.approx(-1 / 3)
    assert summary.coverage == pytest.approx(2 / 3)
    assert summary.mean_range_width == pytest.approx((4 + 1 + 2) / 3)
    assert summary.qwk is not None and summary.pearson is not None


def test_failed_predictions_are_counted_but_excluded() -> None:
    failed = Prediction(strategy="s", example_id="x", human_score=5, min_score=0, max_score=10, error="boom")
    summary = summarize([pred("a", 5, 5), failed])
    assert (summary.n, summary.failed) == (1, 1)
    empty = summarize([failed])
    assert empty.n == 0 and empty.mae is None and empty.worst == []


def test_coverage_counts_range_edges_as_inside() -> None:
    summary = summarize([pred("a", 9, 7, low=5, high=9), pred("b", 5, 7, low=5, high=9)])
    assert summary.coverage == 1.0


def test_qwk_is_skipped_for_mixed_scales() -> None:
    mixed = summarize([pred("a", 5, 5, scale=(0, 10)), pred("b", 2, 2, scale=(0, 4))])
    assert mixed.qwk is None
    assert summarize([pred("a", 5, 5), pred("b", 2, 3)]).qwk is not None


def test_worst_misses_are_sorted_by_error() -> None:
    summary = summarize([pred("a", 5, 6), pred("b", 5, 9), pred("c", 5, 4)], worst_n=2)
    assert [p.example_id for p in summary.worst] == ["b", "a"]


def test_evidence_verified_rate() -> None:
    summary = summarize([
        pred("a", 5, 5, evidence_total=4, evidence_verified=3),
        pred("b", 5, 5, evidence_total=4, evidence_verified=4),
    ])
    assert summary.evidence_verified_rate == pytest.approx(7 / 8)
    assert summarize([pred("a", 5, 5)]).evidence_verified_rate is None


def crit(name, predicted, rank, human=None, human_rank=None):
    return CriterionPrediction(
        name=name, max_points=10, predicted=predicted, predicted_min=predicted,
        predicted_max=predicted, predicted_rank=rank, human=human, human_rank=human_rank,
    )


def test_per_criterion_agreement_only_counts_criteria_with_human_scores() -> None:
    summary = summarize([
        pred("a", 5, 5, criteria={"t": crit("Thesis", 8, 2, 8, 2), "s": crit("Style", 4, 1)}),
        pred("b", 5, 5, criteria={"t": crit("Thesis", 5, 1, 9, 2), "s": crit("Style", 4, 1)}),
        pred("c", 5, 5, criteria={"t": crit("Thesis", 0, 0, 5, 2)}),
    ])
    assert set(summary.criteria) == {"t"}  # Style has no human scores
    thesis = summary.criteria["t"]
    assert thesis.n == 3
    assert thesis.mae == pytest.approx((0 + 4 + 5) / 3)
    assert thesis.exact == pytest.approx(1 / 3)
    assert thesis.adjacent == pytest.approx(2 / 3)
