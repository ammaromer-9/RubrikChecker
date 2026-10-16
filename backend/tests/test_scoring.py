import pytest

from app.schemas.rubric import Criterion
from app.services.scoring import aggregate_criterion, aggregate_overall, level_rank


def criterion(points: list[float]) -> Criterion:
    return Criterion(
        id="c", name="C", max_points=max(points),
        levels=[{"label": f"L{i}", "points": p} for i, p in enumerate(points)],
    )


FOUR_LEVELS = criterion([0, 4, 7, 10])


def test_odd_runs_median_and_range() -> None:
    agg = aggregate_criterion(FOUR_LEVELS, [7, 10, 7])
    assert (agg.median, agg.minimum, agg.maximum) == (7, 7, 10)
    assert not agg.uncertain  # adjacent levels


def test_even_runs_median_is_the_midpoint() -> None:
    agg = aggregate_criterion(FOUR_LEVELS, [4, 7])
    assert agg.median == 5.5


@pytest.mark.parametrize(
    ("runs", "uncertain"),
    [
        ([10, 10, 10], False),
        ([7, 10], False),   # one level apart
        ([4, 10], True),    # two levels apart
        ([0, 4, 7], True),
        ([0, 4], False),
        ([0, 10], True),
    ],
)
def test_uncertain_when_runs_differ_by_more_than_one_level(runs: list[float], uncertain: bool) -> None:
    assert aggregate_criterion(FOUR_LEVELS, runs).uncertain is uncertain


def test_distance_is_counted_in_levels_not_points() -> None:
    uneven = criterion([0, 1, 10])
    assert not aggregate_criterion(uneven, [0, 1]).uncertain
    assert aggregate_criterion(uneven, [0, 10]).uncertain  # 2 levels apart
    assert not aggregate_criterion(uneven, [1, 10]).uncertain  # 1 level apart despite 9 points


def test_levels_with_equal_points_share_a_rank() -> None:
    tied = criterion([0, 5, 5, 10])
    assert level_rank(tied, 5) == 1
    assert not aggregate_criterion(tied, [5, 10]).uncertain


def test_single_run_is_never_uncertain() -> None:
    agg = aggregate_criterion(FOUR_LEVELS, [7])
    assert (agg.median, agg.minimum, agg.maximum, agg.uncertain) == (7, 7, 7, False)


def test_representative_run_is_closest_to_the_median() -> None:
    assert aggregate_criterion(FOUR_LEVELS, [10, 4, 7]).representative == 2


def test_no_runs_is_an_error() -> None:
    with pytest.raises(ValueError):
        aggregate_criterion(FOUR_LEVELS, [])


def test_overall_sums_medians_and_range_bounds() -> None:
    a = aggregate_criterion(FOUR_LEVELS, [7, 10, 7])   # median 7, 7-10
    b = aggregate_criterion(FOUR_LEVELS, [4, 4, 7])    # median 4, 4-7
    overall = aggregate_overall([a, b])
    assert (overall.median, overall.minimum, overall.maximum) == (11, 11, 17)
