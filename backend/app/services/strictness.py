"""Teacher strictness: extra guidance for the grader on borderline calls.

This is a nudge, not a dial. It tells the model which way to lean when a draft sits
between two rubric levels. It never changes the rubric: the model still picks one of the
confirmed levels and the points still come from that level.
"""

from __future__ import annotations

from app.schemas.strictness import Strictness

_BORDERLINE_NOTE = (
    "This only affects borderline calls. A draft that clearly meets, or clearly misses, a "
    "level's description still gets that level."
)

_GUIDANCE: dict[str, str] = {
    "standard": "",  # the unmodified grader: rubric descriptions only
    "strict": (
        "Grading style: this student's teacher is a strict grader. Apply the level "
        "descriptions exactly as written and require a description to be fully met before "
        "you choose that level. When the draft falls between two levels, or you are unsure, "
        "choose the lower one. Give credit only for what the draft actually shows, not for "
        "effort or intent. Do not add standards that the level descriptions do not contain. "
        + _BORDERLINE_NOTE
    ),
    "lenient": (
        "Grading style: this student's teacher is a lenient grader. Give credit for "
        "reasonable attempts, and treat a description as met when it is mostly met. When the "
        "draft falls between two levels, or you are unsure, choose the higher one. Still "
        "choose only among the listed levels, and never credit something the draft does "
        "not do. " + _BORDERLINE_NOTE
    ),
}


def guidance_for(strictness: Strictness | str) -> str:
    """Prompt text for a strictness level; empty for "standard"."""
    try:
        return _GUIDANCE[strictness]
    except KeyError:
        raise ValueError(f"Unknown strictness {strictness!r}") from None
