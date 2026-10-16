"""Holistic grading: one LLM call grades every criterion of the rubric at once.

This exists to be compared against the app's per-criterion strategy.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, Field, create_model

from app.prompts.loader import load_prompt
from app.schemas.grading import EvidenceQuote
from app.schemas.rubric import Criterion, Rubric
from app.services.feedback import levels_text
from app.services.grader import SYSTEM_PROMPT
from app.services.llm_client import LLMClient, LLMError


def holistic_schema_for(rubric: Rubric, enforce_evidence: bool) -> type[BaseModel]:
    """{"criteria": {<criterion id>: {reasoning, level_label, evidence}}} with each
    `level_label` restricted to that criterion's labels."""
    fields = {}
    for criterion in rubric.criteria:
        labels = tuple(level.label for level in criterion.levels)
        evidence = (
            (list[EvidenceQuote], Field(min_length=1))
            if enforce_evidence
            else (list[EvidenceQuote], Field(default_factory=list))
        )
        item = create_model(
            f"Holistic_{criterion.id}",
            reasoning=(str, Field(min_length=1)),
            level_label=(Literal[labels], ...),
            evidence=evidence,
        )
        fields[criterion.id] = (item, ...)
    criteria_model = create_model("HolisticCriteria", **fields)  # type: ignore[call-overload]
    return create_model("HolisticGrade", criteria=(criteria_model, ...))  # type: ignore[call-overload,no-any-return]


def _rubric_text(rubric: Rubric) -> str:
    blocks = []
    for criterion in rubric.criteria:
        blocks.append(
            f"Criterion ID: {criterion.id}\nCriterion: {criterion.name} "
            f"(maximum {criterion.max_points:g} points)\n{levels_text(criterion)}"
        )
    return "\n\n".join(blocks)


def _json_shape(rubric: Rubric, with_evidence: bool) -> str:
    lines = ['{', '  "criteria": {']
    for index, criterion in enumerate(rubric.criteria):
        labels = " | ".join(level.label for level in criterion.levels)
        parts = [
            '"reasoning": "Step-by-step comparison of the draft to the level descriptions"',
            f'"level_label": "<exactly one of: {labels}>"',
        ]
        if with_evidence:
            parts.append('"evidence": [{"quote": "exact words copied from the draft", "supports": "met"}]')
        comma = "," if index < len(rubric.criteria) - 1 else ""
        lines.append(f'    "{criterion.id}": {{{", ".join(parts)}}}{comma}')
    lines += ["  }", "}"]
    return "\n".join(lines)


_EVIDENCE_RULES = (
    '- For each criterion, "evidence" holds 1 to 4 short quotes (a clause or sentence each) that '
    'justify your choice. Every quote must be copied character-for-character from the draft; never '
    'paraphrase, never join separate passages, never use "...". Use "supports": "met" for a quote '
    'showing the draft meets the criterion and "not_met" for one showing where it falls short.'
)


async def grade_holistic_once(
    llm: LLMClient, rubric: Rubric, *, instructions: str, draft: str, enforce_evidence: bool
) -> dict[str, tuple[float, list[EvidenceQuote]]]:
    """Returns {criterion id: (points, evidence)} from a single LLM call."""
    prompt = load_prompt("grade_holistic")
    result = await llm.generate_structured(
        holistic_schema_for(rubric, enforce_evidence),
        purpose="grade_holistic",
        system=SYSTEM_PROMPT,
        prompt=prompt.render(
            instructions=instructions,
            rubric_text=_rubric_text(rubric),
            json_shape=_json_shape(rubric, enforce_evidence),
            draft=draft,
            evidence_rules=_EVIDENCE_RULES if enforce_evidence else "",
        ),
        prompt_version=prompt.version,
        max_tokens=32_000,
    )
    graded: dict[str, tuple[float, list[EvidenceQuote]]] = {}
    for criterion in rubric.criteria:
        item = getattr(result.criteria, criterion.id)  # type: ignore[attr-defined]
        points = _points_for(criterion, item.level_label)
        graded[criterion.id] = (points, list(item.evidence))
    return graded


def _points_for(criterion: Criterion, label: str) -> float:
    return next(level.points for level in criterion.levels if level.label == label)


async def grade_holistic_runs(
    llm: LLMClient,
    rubric: Rubric,
    *,
    instructions: str,
    draft: str,
    num_runs: int,
    concurrency: int,
    enforce_evidence: bool,
) -> list[dict[str, tuple[float, list[EvidenceQuote]]]]:
    """`num_runs` independent holistic gradings. Failed runs are dropped; if all fail,
    the first error is raised."""
    semaphore = asyncio.Semaphore(concurrency)

    async def one() -> dict[str, tuple[float, list[EvidenceQuote]]]:
        async with semaphore:
            return await grade_holistic_once(
                llm, rubric, instructions=instructions, draft=draft, enforce_evidence=enforce_evidence
            )

    outcomes = await asyncio.gather(*(one() for _ in range(num_runs)), return_exceptions=True)
    runs = [o for o in outcomes if isinstance(o, dict)]
    if not runs:
        first = next(o for o in outcomes if isinstance(o, LLMError))
        raise first
    for outcome in outcomes:
        if isinstance(outcome, BaseException) and not isinstance(outcome, LLMError):
            raise outcome
    return runs
