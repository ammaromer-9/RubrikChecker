"""Compare two gradings of the same assignment: what changed, and what got fixed.

Pure functions over `GradingRead` objects, so they are easy to test without a database.
"""

from __future__ import annotations

from app.schemas.comparison import (
    ComparisonRead,
    CriterionChange,
    HistoryCriterion,
    HistoryGrading,
    HistoryRead,
    HistoryVersion,
    OverallChange,
    RequirementChange,
    ResolvedIssue,
    VersionRef,
)
from app.schemas.grading import CriterionResultRead, GradingRead
from app.schemas.requirements import CheckResult

_EPSILON = 1e-9


def ranges_overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> bool:
    return a_min <= b_max and b_min <= a_max


def _status(change: float) -> str:
    if change > _EPSILON:
        return "improved"
    if change < -_EPSILON:
        return "declined"
    return "unchanged"


def _lost_points(result: CriterionResultRead) -> bool:
    return result.median_points < result.max_points - _EPSILON


def _criterion_change(
    previous: CriterionResultRead | None, current: CriterionResultRead | None
) -> CriterionChange:
    anchor = current or previous
    assert anchor is not None
    if previous is None or current is None:
        return CriterionChange(
            criterion_id=anchor.criterion_id, name=anchor.name, max_points=anchor.max_points,
            previous_points=previous.median_points if previous else None,
            current_points=current.median_points if current else None,
            change=None, status="new" if previous is None else "removed",
            ranges_overlap=False, uncertain=anchor.uncertain, resolved=False, issue=None,
        )
    change = current.median_points - previous.median_points
    resolved = _lost_points(previous) and not _lost_points(current)
    return CriterionChange(
        criterion_id=current.criterion_id,
        name=current.name,
        max_points=current.max_points,
        previous_points=previous.median_points,
        current_points=current.median_points,
        change=change,
        status=_status(change),  # type: ignore[arg-type]
        ranges_overlap=ranges_overlap(
            previous.min_points, previous.max_points_scored,
            current.min_points, current.max_points_scored,
        ),
        uncertain=previous.uncertain or current.uncertain,
        resolved=resolved,
        issue=previous.feedback.whats_missing if previous.feedback and _lost_points(previous) else None,
    )


def _requirement_key(check: CheckResult) -> str:
    return f"{check.requirement.type}:{check.requirement.description.strip().casefold()}"


def _requirement_change(previous: CheckResult | None, current: CheckResult | None) -> RequirementChange:
    anchor = current or previous
    assert anchor is not None
    if previous is None:
        status = "new"
    elif current is None:
        status = "removed"
    elif current.passed and not previous.passed:
        status = "resolved"
    elif previous.passed and not current.passed:
        status = "regressed"
    else:
        status = "still_passing" if current.passed else "still_failing"
    return RequirementChange(
        description=anchor.requirement.description,
        previously_passed=previous.passed if previous else None,
        now_passed=current.passed if current else None,
        status=status,  # type: ignore[arg-type]
        details=anchor.details,
    )


def compare_gradings(previous: GradingRead, current: GradingRead) -> ComparisonRead:
    prev_by_id = {c.criterion_id: c for c in previous.criteria}
    curr_by_id = {c.criterion_id: c for c in current.criteria}
    # Keep the current rubric's order, then any criteria that no longer exist.
    ordered_ids = [*curr_by_id, *(i for i in prev_by_id if i not in curr_by_id)]
    changes = [_criterion_change(prev_by_id.get(i), curr_by_id.get(i)) for i in ordered_ids]

    resolved = [
        ResolvedIssue(
            criterion_id=c.criterion_id, name=c.name,
            issue=c.issue or "This criterion lost points last time.",
            points_gained=c.change or 0.0,
        )
        for c in changes
        if c.resolved
    ]

    prev_checks = {_requirement_key(c): c for c in previous.instruction_checks}
    curr_checks = {_requirement_key(c): c for c in current.instruction_checks}
    check_keys = [*curr_checks, *(k for k in prev_checks if k not in curr_checks)]
    requirement_changes = [
        _requirement_change(prev_checks.get(k), curr_checks.get(k)) for k in check_keys
    ]

    p, c = previous.overall, current.overall
    assert None not in (p.median, p.min, p.max, c.median, c.min, c.max)
    overall = OverallChange(
        previous_median=p.median, current_median=c.median,  # type: ignore[arg-type]
        change=c.median - p.median,  # type: ignore[operator]
        previous_min=p.min, previous_max=p.max,  # type: ignore[arg-type]
        current_min=c.min, current_max=c.max,  # type: ignore[arg-type]
        max_possible=c.max_possible,
        ranges_overlap=ranges_overlap(p.min, p.max, c.min, c.max),  # type: ignore[arg-type]
    )
    return ComparisonRead(
        assignment_id=current.assignment_id,
        previous=VersionRef(
            submission_id=previous.submission_id, version_number=previous.version_number,
            grading_id=previous.id,
        ),
        current=VersionRef(
            submission_id=current.submission_id, version_number=current.version_number,
            grading_id=current.id,
        ),
        overall=overall,
        criteria=changes,
        resolved_issues=resolved,
        requirement_changes=requirement_changes,
        remaining_fixes=current.top_fixes,
        improved_count=sum(1 for ch in changes if ch.status == "improved"),
        declined_count=sum(1 for ch in changes if ch.status == "declined"),
        unchanged_count=sum(1 for ch in changes if ch.status == "unchanged"),
    )


def build_history(
    *,
    assignment_id: int,
    title: str,
    rubric_criteria: list[HistoryCriterion],
    submissions: list,  # list[Submission], oldest first
    gradings: dict[int, GradingRead],
) -> HistoryRead:
    """One entry per submitted version, with the latest complete grading if it has one."""
    criteria = list(rubric_criteria)
    known = {c.criterion_id for c in criteria}
    for grading in gradings.values():
        for result in grading.criteria:
            if result.criterion_id not in known:  # rubric changed since this version
                known.add(result.criterion_id)
                criteria.append(
                    HistoryCriterion(
                        criterion_id=result.criterion_id, name=result.name, max_points=result.max_points
                    )
                )

    versions = []
    for submission in submissions:
        grading = gradings.get(submission.id)
        versions.append(
            HistoryVersion(
                submission_id=submission.id,
                version_number=submission.version_number,
                created_at=submission.created_at,
                grading=None
                if grading is None
                else HistoryGrading(
                    grading_id=grading.id,
                    overall=grading.overall,
                    criterion_points={r.criterion_id: r.median_points for r in grading.criteria},
                    uncertain=[r.criterion_id for r in grading.criteria if r.uncertain],
                ),
            )
        )
    latest = next((g for g in reversed([gradings.get(s.id) for s in submissions]) if g), None)
    return HistoryRead(
        assignment_id=assignment_id,
        title=title,
        max_possible=sum(c.max_points for c in criteria) if criteria else (
            latest.overall.max_possible if latest else None
        ),
        criteria=criteria,
        versions=versions,
    )
