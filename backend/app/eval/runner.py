"""Run grading strategies over a dataset and collect predictions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.eval.datasets import EvalExample
from app.eval.holistic import grade_holistic_runs
from app.eval.metrics import CriterionPrediction, Prediction
from app.eval.strategies import StrategySpec
from app.schemas.grading import EvidenceQuote
from app.schemas.rubric import Rubric
from app.services.evidence import verify_evidence
from app.services.grader import grade_all_criteria
from app.services.llm_client import CallRecord, LLMClient, LLMError
from app.services.llm_testing import InMemoryCallRecorder
from app.services.rubric_parser import parse_rubric
from app.services.scoring import aggregate_criterion, aggregate_overall, level_rank

# Builds an LLM client for a model name (None = the configured default) that logs to `recorder`.
ClientFactory = Callable[[str | None, InMemoryCallRecorder], LLMClient]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@dataclass
class ResolvedExample:
    example: EvalExample
    rubric: Rubric
    scale_min: float
    scale_max: float
    # Human per-criterion points keyed by the matching rubric criterion id.
    criterion_human: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


async def resolve_rubrics(
    examples: list[EvalExample], llm: LLMClient | None, cache_dir: Path | None
) -> list[ResolvedExample]:
    """Attach a structured rubric to each example, parsing each distinct rubric text once
    (and caching the result on disk so reruns don't pay for it again)."""
    parsed: dict[str, Rubric] = {}
    resolved = []
    for example in examples:
        rubric = example.rubric
        if rubric is None:
            text = example.rubric_text or ""
            if text not in parsed:
                parsed[text] = await _parse_with_cache(llm, text, cache_dir)
            rubric = parsed[text]
        resolved.append(_resolve(example, rubric))
    return resolved


async def _parse_with_cache(llm: LLMClient | None, text: str, cache_dir: Path | None) -> Rubric:
    cache_file = None
    if cache_dir is not None:
        cache_file = cache_dir / f"rubric-{hashlib.sha256(text.encode()).hexdigest()[:16]}.json"
        if cache_file.exists():
            return Rubric.model_validate_json(cache_file.read_text(encoding="utf-8"))
    if llm is None:
        raise RuntimeError("An LLM client is needed to parse the rubric text.")
    rubric = await parse_rubric(llm, text)
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(rubric.model_dump_json(indent=2), encoding="utf-8")
    return rubric


def _resolve(example: EvalExample, rubric: Rubric) -> ResolvedExample:
    by_slug = {}
    for criterion in rubric.criteria:
        by_slug[slug(criterion.id)] = criterion.id
        by_slug.setdefault(slug(criterion.name), criterion.id)
    human: dict[str, float] = {}
    warnings = []
    for key, value in example.criterion_scores.items():
        criterion_id = by_slug.get(slug(key))
        if criterion_id is None:
            warnings.append(f"{example.id}: column 'criterion_{key}' matches no criterion in the rubric.")
        else:
            human[criterion_id] = value
    return ResolvedExample(
        example=example,
        rubric=rubric,
        scale_min=example.min_score,
        scale_max=example.max_score if example.max_score is not None else rubric.total_points,
        criterion_human=human,
        warnings=warnings,
    )


def estimate_calls(
    specs: list[StrategySpec], resolved: list[ResolvedExample], runs: int
) -> dict[str, int]:
    """Number of LLM calls each strategy will make (before retries)."""
    return {
        spec.name: sum(
            runs * (len(r.rubric.criteria) if spec.mode == "per_criterion" else 1) for r in resolved
        )
        for spec in specs
    }


async def predict(
    llm: LLMClient, spec: StrategySpec, item: ResolvedExample, *, runs: int, concurrency: int
) -> Prediction:
    """Grade one essay with one strategy and score it against the human grade."""
    rubric, example = item.rubric, item.example
    points: dict[str, list[float]] = {c.id: [] for c in rubric.criteria}
    quotes: list[list[EvidenceQuote]] = []
    try:
        if spec.mode == "per_criterion":
            by_criterion = await grade_all_criteria(
                llm, rubric, instructions=example.instructions, draft=example.draft,
                num_runs=runs, concurrency=concurrency, grading_id=None,
                prompt_name="grade_criterion" if spec.evidence else "grade_criterion_no_evidence",
                enforce_evidence=spec.evidence,
            )
            for criterion_id, criterion_runs in by_criterion.items():
                points[criterion_id] = [run.points for run in criterion_runs]
                quotes += [run.grade.evidence for run in criterion_runs]
        else:
            holistic_runs = await grade_holistic_runs(
                llm, rubric, instructions=example.instructions, draft=example.draft,
                num_runs=runs, concurrency=concurrency, enforce_evidence=spec.evidence,
            )
            for graded in holistic_runs:
                for criterion_id, (value, evidence) in graded.items():
                    points[criterion_id].append(value)
                    quotes.append(evidence)
    except LLMError as exc:
        return Prediction(
            strategy=spec.name, example_id=example.id, human_score=example.human_score,
            min_score=item.scale_min, max_score=item.scale_max, error=str(exc)[:300],
        )

    criteria: dict[str, CriterionPrediction] = {}
    aggregates = []
    for criterion in rubric.criteria:
        aggregate = aggregate_criterion(criterion, points[criterion.id])
        aggregates.append(aggregate)
        human = item.criterion_human.get(criterion.id)
        criteria[criterion.id] = CriterionPrediction(
            name=criterion.name, max_points=criterion.max_points,
            predicted=aggregate.median, predicted_min=aggregate.minimum,
            predicted_max=aggregate.maximum,
            predicted_rank=level_rank(criterion, aggregate.median),
            human=human, human_rank=None if human is None else level_rank(criterion, human),
        )
    overall = aggregate_overall(aggregates)

    # Rubric points -> the human scale, clamped to what a human could have given.
    factor = item.scale_max / rubric.total_points

    def to_scale(value: float) -> float:
        return min(max(value * factor, item.scale_min), item.scale_max)

    flat = [q for group in quotes for q in group]
    return Prediction(
        strategy=spec.name, example_id=example.id, human_score=example.human_score,
        min_score=item.scale_min, max_score=item.scale_max,
        predicted=to_scale(overall.median), predicted_min=to_scale(overall.minimum),
        predicted_max=to_scale(overall.maximum), criteria=criteria,
        evidence_total=len(flat),
        evidence_verified=_count_verified(example.draft, quotes),
    )


def _count_verified(draft: str, quote_groups: list[list[EvidenceQuote]]) -> int:
    return sum(v.verified for group in quote_groups for v in verify_evidence(draft, group))


@dataclass
class Usage:
    calls: int
    failed_calls: int
    input_tokens: int
    output_tokens: int
    mean_latency_ms: float


def usage_from(records: list[CallRecord]) -> Usage:
    return Usage(
        calls=len(records),
        failed_calls=sum(not r.success for r in records),
        input_tokens=sum(r.input_tokens for r in records),
        output_tokens=sum(r.output_tokens for r in records),
        mean_latency_ms=sum(r.latency_ms for r in records) / len(records) if records else 0.0,
    )


@dataclass
class StrategyResult:
    spec: StrategySpec
    predictions: list[Prediction]
    usage: Usage


async def run_strategy(
    spec: StrategySpec,
    resolved: list[ResolvedExample],
    *,
    make_client: ClientFactory,
    runs: int,
    essay_concurrency: int,
    call_concurrency: int,
    done: dict[str, Prediction] | None = None,
    on_prediction: Callable[[Prediction], None] | None = None,
) -> StrategyResult:
    """Grade every example with `spec`. Examples already in `done` are not graded again."""
    recorder = InMemoryCallRecorder()
    llm = make_client(spec.model, recorder)
    done = done or {}
    semaphore = asyncio.Semaphore(essay_concurrency)

    async def one(item: ResolvedExample) -> Prediction:
        previous = done.get(item.example.id)
        if previous is not None:
            return previous
        async with semaphore:
            prediction = await predict(llm, spec, item, runs=runs, concurrency=call_concurrency)
        if on_prediction:
            on_prediction(prediction)
        return prediction

    predictions = await asyncio.gather(*(one(item) for item in resolved))
    return StrategyResult(spec=spec, predictions=list(predictions), usage=usage_from(recorder.calls))


# --- Saving progress so an interrupted (and paid-for) run can resume ---------------------


def prediction_to_json(prediction: Prediction) -> str:
    return json.dumps(asdict(prediction))


def prediction_from_json(line: str) -> Prediction:
    data = json.loads(line)
    criteria = data.get("criteria")
    data["criteria"] = (
        None if criteria is None else {k: CriterionPrediction(**v) for k, v in criteria.items()}
    )
    return Prediction(**data)


def load_done(path: Path) -> dict[str, dict[str, Prediction]]:
    """Successful predictions already saved: {strategy name: {example id: prediction}}."""
    done: dict[str, dict[str, Prediction]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                prediction = prediction_from_json(line)
                if prediction.ok:
                    done.setdefault(prediction.strategy, {})[prediction.example_id] = prediction
    return done
