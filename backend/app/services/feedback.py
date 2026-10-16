"""Academic-integrity-safe feedback: guidance, never drafted text.

Two layers keep feedback from doing the student's work:
1. The prompt forbids rewritten sentences, samples, and anything pasteable.
2. `find_drafted_content` is a deterministic post-check that flags long passages in
   quotation marks (or blockquotes / code fences) that do not come from the
   student's own draft. Flagged feedback is regenerated once, then replaced by a
   generic hint built from the rubric.
"""

from __future__ import annotations

import logging
import re

from app.prompts.loader import load_prompt
from app.schemas.grading import CriterionFeedback, FeedbackDraft, TopFix, VerifiedEvidence
from app.schemas.rubric import Criterion, Level
from app.services.evidence import contains_text
from app.services.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a writing coach. You help students improve their own work by pointing out "
    "gaps and asking guiding questions. You never write or rewrite their text. "
    "You output only a single valid JSON object."
)

_QUOTED_RE = re.compile(r'"([^"]+)"|“([^”]+)”')
_BLOCKQUOTE_RE = re.compile(r"^[ \t]*>[ \t]?(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _word_count(text: str) -> int:
    return len(text.split())


def find_drafted_content(texts: list[str], draft: str, max_words: int = 25) -> list[str]:
    """Return passages longer than `max_words` that look like drafted content.

    A passage counts when it sits in quotation marks, a markdown blockquote, or a code
    fence, exceeds `max_words` words, and does NOT appear in the student's draft.
    Quoting the student's own long passage back to them is fine.
    """
    flagged: list[str] = []
    for text in texts:
        candidates = [a or b for a, b in _QUOTED_RE.findall(text)]
        candidates += _BLOCKQUOTE_RE.findall(text)
        candidates += _CODE_FENCE_RE.findall(text)
        for passage in candidates:
            if _word_count(passage) > max_words and not contains_text(draft, passage):
                flagged.append(passage.strip())
    return flagged


def _feedback_texts(feedback: FeedbackDraft) -> list[str]:
    return [feedback.whats_missing, feedback.where_in_draft, *feedback.guiding_questions]


def level_line(level: Level) -> str:
    line = f"- {level.label} ({level.points:g} points)"
    return f"{line}: {level.description}" if level.description else line


def levels_text(criterion: Criterion) -> str:
    ordered = sorted(criterion.levels, key=lambda level: -level.points)
    return "\n".join(level_line(level) for level in ordered)


def next_level_up(criterion: Criterion, current_points: float) -> Level:
    higher = [level for level in criterion.levels if level.points > current_points]
    if higher:
        return min(higher, key=lambda level: level.points)
    return max(criterion.levels, key=lambda level: level.points)


def fallback_feedback(criterion: Criterion, current_points: float) -> CriterionFeedback:
    """Generic, rubric-based guidance used when model feedback is unavailable or unsafe."""
    target = next_level_up(criterion, current_points)
    description = target.description or f"the '{target.label}' level"
    return CriterionFeedback(
        whats_missing=(
            f"This criterion scored below full marks. The rubric describes the next level "
            f"('{target.label}') as: {description}"
        ),
        where_in_draft="",
        evidence_indexes=[],
        guiding_questions=[
            f"Which parts of your draft show \"{criterion.name}\" as the rubric describes it?",
            "Where does your draft fall short of the next level's description?",
        ],
        is_fallback=True,
    )


def _evidence_text(evidence: list[VerifiedEvidence]) -> str:
    verified = [item for item in evidence if item.verified]
    if not verified:
        return "(none)"
    return "\n".join(
        f'{number}. [{item.supports}] "{item.quote}"' for number, item in enumerate(verified, 1)
    )


async def generate_feedback(
    llm: LLMClient,
    *,
    instructions: str,
    draft: str,
    criterion: Criterion,
    median_points: float,
    level_label: str,
    reasoning: str,
    evidence: list[VerifiedEvidence],
    max_quoted_words: int,
    grading_id: int | None = None,
) -> CriterionFeedback:
    """Feedback for one criterion that lost points. Never raises for model problems:
    any failure degrades to `fallback_feedback`."""
    prompt = load_prompt("feedback")
    verified_count = sum(1 for item in evidence if item.verified)

    def render(extra_notice: str) -> str:
        return prompt.render(
            instructions=instructions,
            criterion_name=criterion.name,
            median_points=f"{median_points:g}",
            max_points=f"{criterion.max_points:g}",
            level_label=level_label,
            next_level_text=level_line(next_level_up(criterion, median_points)),
            levels_text=levels_text(criterion),
            reasoning=reasoning,
            evidence_text=_evidence_text(evidence),
            draft=draft,
            extra_notice=extra_notice,
        )

    notice = ""
    for _ in range(2):
        try:
            result = await llm.generate_structured(
                FeedbackDraft,
                purpose="feedback",
                system=SYSTEM_PROMPT,
                prompt=render(notice),
                prompt_version=prompt.version,
                grading_id=grading_id,
                max_tokens=1500,
                temperature=0.3,
            )
        except LLMError as exc:
            logger.warning("Feedback generation failed for %s: %s", criterion.id, exc)
            break
        flagged = find_drafted_content(_feedback_texts(result), draft, max_quoted_words)
        if not flagged:
            valid = [i for i in result.evidence_indexes if 1 <= i <= verified_count]
            return CriterionFeedback(**{**result.model_dump(), "evidence_indexes": valid})
        logger.warning("Feedback for %s contained drafted-looking text; retrying", criterion.id)
        notice = (
            "\nIMPORTANT: your previous reply put long passages in quotation marks that the "
            "student did not write. That looks like drafted text. Remove it. Only describe "
            "gaps and ask questions; quote nothing except short exact phrases from the draft."
        )
    return fallback_feedback(criterion, median_points)


def top_fixes(
    results: list[tuple[Criterion, float, CriterionFeedback | None]], limit: int = 3
) -> list[TopFix]:
    """The criteria with the most points at stake, biggest first."""
    stakes = [
        TopFix(
            criterion_id=criterion.id,
            name=criterion.name,
            points_at_stake=criterion.max_points - median,
            summary=feedback.whats_missing if feedback else "",
        )
        for criterion, median, feedback in results
        if criterion.max_points - median > 0
    ]
    stakes.sort(key=lambda fix: -fix.points_at_stake)
    return stakes[:limit]
