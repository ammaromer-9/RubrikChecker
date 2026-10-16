"""Per-criterion grading: N runs per criterion, aggregated, evidence-checked, with feedback.

Flow of `run_grading`:
  1. create the Grading row (committed first, so llm_calls can reference it)
  2. run the deterministic instruction checks
  3. grade every criterion N times, concurrently under a semaphore
  4. aggregate runs and verify evidence quotes against the draft
  5. generate feedback for criteria that lost points
  6. save everything in one transaction
Any failure marks the grading `failed` and re-raises.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Assignment, CriterionResult, Grading, InstructionCheckResult, Submission
from app.prompts.loader import load_prompt
from app.schemas.grading import (
    CriterionFeedback,
    CriterionGrade,
    EvidenceQuote,
    VerifiedEvidence,
)
from app.schemas.requirements import CheckResult, RequirementList
from app.schemas.rubric import Criterion, Rubric
from app.services.evidence import verify_evidence
from app.services.feedback import generate_feedback, levels_text
from app.services.instruction_checks import evaluate_requirements
from app.services.llm_client import LLMClient, LLMError
from app.services.requirements_extractor import extract_requirements
from app.services.scoring import aggregate_criterion, aggregate_overall

logger = logging.getLogger(__name__)

STRATEGY = "per_criterion"
SYSTEM_PROMPT = (
    "You are a careful, consistent grader. You grade strictly against the rubric level "
    "descriptions you are given and nothing else. You output only a single valid JSON object."
)


class RubricNotConfirmedError(Exception):
    """Grading was requested before the user confirmed the rubric."""


@dataclass(frozen=True)
class CriterionRun:
    grade: CriterionGrade
    points: float


def grade_schema_for(criterion: Criterion, enforce_evidence: bool = False) -> type[CriterionGrade]:
    """A CriterionGrade whose `level_label` must be one of this criterion's labels.

    A wrong label becomes a validation error that lists the allowed values, which the
    LLM client feeds back to the model on its one retry. With `enforce_evidence`, at
    least one quote is required too (used by the evaluation strategies; production
    allows none because a missing feature may have nothing to quote).
    """
    labels = tuple(level.label for level in criterion.levels)
    evidence = (
        (list[EvidenceQuote], Field(min_length=1))
        if enforce_evidence
        else (list[EvidenceQuote], Field(default_factory=list))
    )
    return create_model(  # type: ignore[call-overload,no-any-return]
        "CriterionGradeForCriterion",
        __base__=CriterionGrade,
        level_label=(Literal[labels], ...),
        evidence=evidence,
    )


async def grade_criterion_once(
    llm: LLMClient,
    *,
    instructions: str,
    draft: str,
    criterion: Criterion,
    grading_id: int | None,
    prompt_name: str = "grade_criterion",
    enforce_evidence: bool = False,
) -> CriterionRun:
    prompt = load_prompt(prompt_name)
    grade = await llm.generate_structured(
        grade_schema_for(criterion, enforce_evidence),
        purpose="grade_criterion",
        system=SYSTEM_PROMPT,
        prompt=prompt.render(
            instructions=instructions,
            criterion_id=criterion.id,
            criterion_name=criterion.name,
            max_points=f"{criterion.max_points:g}",
            levels_text=levels_text(criterion),
            draft=draft,
        ),
        prompt_version=prompt.version,
        grading_id=grading_id,
    )
    # The rubric, not the model, is the source of truth for what a level is worth.
    level = next(lvl for lvl in criterion.levels if lvl.label == grade.level_label)
    return CriterionRun(grade=grade, points=level.points)


async def grade_all_criteria(
    llm: LLMClient,
    rubric: Rubric,
    *,
    instructions: str,
    draft: str,
    num_runs: int,
    concurrency: int,
    grading_id: int | None,
    prompt_name: str = "grade_criterion",
    enforce_evidence: bool = False,
) -> dict[str, list[CriterionRun]]:
    """Run every criterion `num_runs` times. A failed run is dropped; a criterion with
    no successful run fails the whole grading."""
    semaphore = asyncio.Semaphore(concurrency)

    async def one(criterion: Criterion) -> CriterionRun:
        async with semaphore:
            return await grade_criterion_once(
                llm, instructions=instructions, draft=draft, criterion=criterion,
                grading_id=grading_id, prompt_name=prompt_name, enforce_evidence=enforce_evidence,
            )

    jobs = [(c, one(c)) for c in rubric.criteria for _ in range(num_runs)]
    outcomes = await asyncio.gather(*(job for _, job in jobs), return_exceptions=True)

    runs: dict[str, list[CriterionRun]] = {c.id: [] for c in rubric.criteria}
    first_error: dict[str, Exception] = {}
    for (criterion, _), outcome in zip(jobs, outcomes, strict=True):
        if isinstance(outcome, LLMError):
            first_error.setdefault(criterion.id, outcome)
        elif isinstance(outcome, BaseException):
            raise outcome
        else:
            runs[criterion.id].append(outcome)

    for criterion_id, criterion_runs in runs.items():
        if not criterion_runs:
            raise first_error[criterion_id]
        if criterion_id in first_error:
            logger.warning("Some grading runs failed for %s; using %d", criterion_id, len(criterion_runs))
    return runs


@dataclass
class GradedCriterion:
    criterion: Criterion
    median: float
    minimum: float
    maximum: float
    uncertain: bool
    chosen_level: str
    confidence: str
    reasoning: str
    run_points: list[float]
    evidence: list[VerifiedEvidence]
    feedback: CriterionFeedback | None = None


def aggregate_runs(
    rubric: Rubric, runs: dict[str, list[CriterionRun]], draft: str
) -> list[GradedCriterion]:
    """Median/range/uncertain per criterion, plus verified evidence from the run that
    is closest to the median."""
    graded = []
    for criterion in rubric.criteria:
        criterion_runs = runs[criterion.id]
        points = [run.points for run in criterion_runs]
        aggregate = aggregate_criterion(criterion, points)
        shown = criterion_runs[aggregate.representative].grade
        graded.append(
            GradedCriterion(
                criterion=criterion,
                median=aggregate.median,
                minimum=aggregate.minimum,
                maximum=aggregate.maximum,
                uncertain=aggregate.uncertain,
                chosen_level=shown.level_label,
                confidence=shown.confidence,
                reasoning=shown.reasoning,
                run_points=points,
                evidence=verify_evidence(draft, shown.evidence),
            )
        )
    return graded


async def _requirements_for(
    llm: LLMClient, assignment: Assignment, grading_id: int
) -> RequirementList:
    """Stored requirements, extracting them now if the user never triggered extraction.
    Instruction checks are a bonus: if extraction fails, grading continues without them."""
    if assignment.requirements_parsed is not None:
        return RequirementList.model_validate(assignment.requirements_parsed)
    try:
        requirements = await extract_requirements(llm, assignment.instructions_text, grading_id)
    except LLMError as exc:
        logger.warning("Could not extract requirements for assignment %s: %s", assignment.id, exc)
        return RequirementList()
    assignment.requirements_parsed = requirements.model_dump(mode="json")
    return requirements


async def run_grading(
    session: AsyncSession,
    llm: LLMClient,
    assignment: Assignment,
    submission: Submission,
    settings: Settings,
    num_runs: int | None = None,
) -> Grading:
    if not assignment.rubric_confirmed or assignment.rubric_parsed is None:
        raise RubricNotConfirmedError("Confirm the rubric before grading.")
    rubric = Rubric.model_validate(assignment.rubric_parsed)
    runs_wanted = num_runs or settings.grading_runs
    prompt_version = f"{load_prompt('grade_criterion').version}+{load_prompt('feedback').version}"

    grading = Grading(
        submission_id=submission.id, strategy=STRATEGY, model=llm.model,
        num_runs=runs_wanted, status="running", prompt_version=prompt_version,
    )
    session.add(grading)
    await session.commit()  # llm_calls rows reference this id from separate sessions
    grading_id = grading.id

    try:
        requirements = await _requirements_for(llm, assignment, grading_id)
        checks = evaluate_requirements(requirements.requirements, submission.draft_text)

        runs = await grade_all_criteria(
            llm, rubric, instructions=assignment.instructions_text, draft=submission.draft_text,
            num_runs=runs_wanted,
            concurrency=settings.grading_concurrency, grading_id=grading_id,
        )
        graded = aggregate_runs(rubric, runs, submission.draft_text)

        semaphore = asyncio.Semaphore(settings.grading_concurrency)

        async def add_feedback(item: GradedCriterion) -> None:
            async with semaphore:
                item.feedback = await generate_feedback(
                    llm, instructions=assignment.instructions_text, draft=submission.draft_text,
                    criterion=item.criterion, median_points=item.median,
                    level_label=item.chosen_level, reasoning=item.reasoning,
                    evidence=item.evidence, max_quoted_words=settings.feedback_max_quoted_words,
                    grading_id=grading_id,
                )

        await asyncio.gather(*(add_feedback(g) for g in graded if g.median < g.criterion.max_points))

        overall = aggregate_overall(
            [aggregate_criterion(g.criterion, g.run_points) for g in graded]
        )
        _save_results(session, grading, graded, checks, overall)
        await session.commit()
    except BaseException as exc:
        await session.rollback()
        failed = await session.get(Grading, grading_id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)[:1000] or type(exc).__name__
            await session.commit()
        raise
    return grading


def _save_results(session, grading, graded, checks: list[CheckResult], overall) -> None:  # type: ignore[no-untyped-def]
    grading.status = "complete"
    grading.overall_median = overall.median
    grading.overall_min = overall.minimum
    grading.overall_max = overall.maximum
    for item in graded:
        session.add(
            CriterionResult(
                grading_id=grading.id,
                criterion_id=item.criterion.id,
                median_points=item.median,
                min_points=item.minimum,
                max_points=item.maximum,
                uncertain=item.uncertain,
                chosen_level=item.chosen_level,
                confidence=item.confidence,
                reasoning=item.reasoning,
                run_points=item.run_points,
                evidence=[e.model_dump() for e in item.evidence],
                feedback=item.feedback.model_dump() if item.feedback else None,
            )
        )
    for check in checks:
        session.add(
            InstructionCheckResult(
                grading_id=grading.id,
                requirement=check.requirement.model_dump(mode="json"),
                passed=check.passed,
                details=check.details,
            )
        )
