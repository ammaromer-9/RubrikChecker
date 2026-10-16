from datetime import UTC, datetime
from types import SimpleNamespace

from app.schemas.comparison import HistoryCriterion
from app.schemas.grading import (
    CriterionFeedback,
    CriterionResultRead,
    GradingRead,
    OverallScore,
    TopFix,
)
from app.schemas.requirements import CheckResult, WordCountRequirement
from app.services.comparison import build_history, compare_gradings, ranges_overlap


def result(cid, median, max_points=10, lo=None, hi=None, uncertain=False, issue=None):
    lo = median if lo is None else lo
    hi = median if hi is None else hi
    feedback = None
    if issue:
        feedback = CriterionFeedback(
            whats_missing=issue, where_in_draft="", guiding_questions=["Why?"]
        )
    return CriterionResultRead(
        criterion_id=cid, name=cid.title(), max_points=max_points, median_points=median,
        min_points=lo, max_points_scored=hi, uncertain=uncertain, chosen_level="x",
        confidence="high", reasoning="r", run_points=[median], evidence=[], feedback=feedback,
    )


def check(description, passed, details="d"):
    return CheckResult(
        requirement=WordCountRequirement(description=description, min_words=5),
        passed=passed, details=details,
    )


def grading(gid, version, results, checks=(), top_fixes=()):
    total = sum(r.median_points for r in results)
    low = sum(r.min_points for r in results)
    high = sum(r.max_points_scored for r in results)
    return GradingRead(
        id=gid, submission_id=gid * 10, assignment_id=1, version_number=version, status="complete",
        error=None, strategy="per_criterion", model="m", num_runs=3, prompt_version="p",
        created_at=datetime.now(UTC),
        overall=OverallScore(median=total, min=low, max=high,
                             max_possible=sum(r.max_points for r in results)),
        draft_text="", criteria=results, instruction_checks=list(checks), top_fixes=list(top_fixes),
    )


def test_ranges_overlap() -> None:
    assert ranges_overlap(5, 8, 8, 10)  # touching counts
    assert ranges_overlap(0, 10, 4, 6)
    assert not ranges_overlap(0, 4, 5, 9)


def test_statuses_changes_and_overall() -> None:
    before = grading(1, 1, [result("a", 4), result("b", 8), result("c", 6)])
    after = grading(2, 2, [result("a", 7), result("b", 8), result("c", 5)])
    comparison = compare_gradings(before, after)

    by_id = {c.criterion_id: c for c in comparison.criteria}
    assert (by_id["a"].status, by_id["a"].change) == ("improved", 3)
    assert (by_id["b"].status, by_id["b"].change) == ("unchanged", 0)
    assert (by_id["c"].status, by_id["c"].change) == ("declined", -1)
    assert (comparison.improved_count, comparison.unchanged_count, comparison.declined_count) == (1, 1, 1)

    assert comparison.overall.previous_median == 18 and comparison.overall.current_median == 20
    assert comparison.overall.change == 2
    assert comparison.previous.version_number == 1 and comparison.current.version_number == 2
    assert comparison.previous.grading_id == 1 and comparison.current.grading_id == 2


def test_issue_is_resolved_only_when_full_marks_are_reached() -> None:
    before = grading(1, 1, [
        result("a", 4, issue="No evidence"),
        result("b", 4, issue="Weak structure"),
        result("c", 10),
    ])
    after = grading(2, 2, [result("a", 10), result("b", 7), result("c", 10)])
    comparison = compare_gradings(before, after)

    assert [(r.criterion_id, r.issue, r.points_gained) for r in comparison.resolved_issues] == [
        ("a", "No evidence", 6)
    ]
    by_id = {c.criterion_id: c for c in comparison.criteria}
    assert by_id["a"].resolved and not by_id["b"].resolved and not by_id["c"].resolved
    assert by_id["b"].issue == "Weak structure"  # still shows what it was about
    assert by_id["c"].issue is None  # never lost points


def test_resolved_issue_without_saved_feedback_still_listed() -> None:
    comparison = compare_gradings(grading(1, 1, [result("a", 4)]), grading(2, 2, [result("a", 10)]))
    assert comparison.resolved_issues[0].issue == "This criterion lost points last time."


def test_noise_flag_compares_run_ranges() -> None:
    noisy_before = grading(1, 1, [result("a", 5, lo=3, hi=8)])
    noisy_after = grading(2, 2, [result("a", 7, lo=5, hi=9)])
    comparison = compare_gradings(noisy_before, noisy_after)
    assert comparison.criteria[0].ranges_overlap and comparison.overall.ranges_overlap

    clear_after = grading(3, 3, [result("a", 10, lo=9, hi=10)])
    clear = compare_gradings(noisy_before, clear_after)
    assert not clear.criteria[0].ranges_overlap and not clear.overall.ranges_overlap


def test_uncertain_if_either_version_was() -> None:
    comparison = compare_gradings(
        grading(1, 1, [result("a", 5, uncertain=True)]), grading(2, 2, [result("a", 6)])
    )
    assert comparison.criteria[0].uncertain


def test_added_and_removed_criteria() -> None:
    before = grading(1, 1, [result("a", 5), result("old", 3)])
    after = grading(2, 2, [result("a", 5), result("fresh", 8)])
    by_id = {c.criterion_id: c for c in compare_gradings(before, after).criteria}
    assert by_id["fresh"].status == "new" and by_id["fresh"].change is None
    assert by_id["old"].status == "removed" and by_id["old"].current_points is None
    assert list(by_id) == ["a", "fresh", "old"]  # current order first


def test_requirement_changes() -> None:
    before = grading(1, 1, [result("a", 5)], checks=[
        check("At least 50 words", False), check("Has intro", True),
        check("Cites 3 sources", False), check("Old rule", True),
    ])
    after = grading(2, 2, [result("a", 5)], checks=[
        check("At least 50 words", True), check("Has intro", False),
        check("Cites 3 sources", False), check("New rule", True),
    ])
    statuses = {r.description: r.status for r in compare_gradings(before, after).requirement_changes}
    assert statuses == {
        "At least 50 words": "resolved", "Has intro": "regressed",
        "Cites 3 sources": "still_failing", "New rule": "new", "Old rule": "removed",
    }


def test_remaining_fixes_come_from_the_current_grading() -> None:
    fix = TopFix(criterion_id="a", name="A", points_at_stake=2, summary="s")
    comparison = compare_gradings(grading(1, 1, [result("a", 5)]), grading(2, 2, [result("a", 8)], top_fixes=[fix]))
    assert comparison.remaining_fixes == [fix]


def test_history_marks_ungraded_versions_and_adds_dropped_criteria() -> None:
    submissions = [
        SimpleNamespace(id=10, version_number=1, created_at=datetime.now(UTC)),
        SimpleNamespace(id=20, version_number=2, created_at=datetime.now(UTC)),
    ]
    history = build_history(
        assignment_id=1, title="Essay",
        rubric_criteria=[HistoryCriterion(criterion_id="a", name="A", max_points=10)],
        submissions=submissions,
        gradings={10: grading(1, 1, [result("a", 5), result("gone", 2, uncertain=True)])},
    )
    assert [v.grading is None for v in history.versions] == [False, True]
    assert [c.criterion_id for c in history.criteria] == ["a", "gone"]
    assert history.versions[0].grading.uncertain == ["gone"]
    assert history.versions[0].grading.criterion_points == {"a": 5, "gone": 2}
    assert history.max_possible == 20
