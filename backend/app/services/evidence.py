"""Verify that quotes cited by the grader really appear in the student's draft.

Matching ignores whitespace differences (line breaks, repeated spaces) and curly vs
straight quotes, because models and word processors often change those. Everything
else must match exactly. Offsets always refer to the original, unmodified draft.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.schemas.grading import EvidenceQuote, VerifiedEvidence

# Single-character folds only, so indexes stay aligned with the original text.
_CHAR_FOLD = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', " ": " "}
)


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Fold quotes and collapse whitespace runs to one space.

    Returns the normalized text and, for each of its characters, the index of the
    corresponding character in the original text.
    """
    chars: list[str] = []
    index_map: list[int] = []
    previous_was_space = False
    for index, char in enumerate(text.translate(_CHAR_FOLD)):
        if char.isspace():
            if previous_was_space:
                continue
            char = " "
            previous_was_space = True
        else:
            previous_was_space = False
        chars.append(char)
        index_map.append(index)
    return "".join(chars), index_map


def normalize(text: str) -> str:
    return normalize_with_map(text)[0].strip()


def contains_text(draft: str, passage: str) -> bool:
    """True if `passage` appears in `draft`, ignoring whitespace and quote style."""
    needle = normalize(passage)
    return bool(needle) and needle in normalize(draft)


def verify_evidence(draft: str, items: Iterable[EvidenceQuote]) -> list[VerifiedEvidence]:
    """Locate each quote in the draft. Unfound quotes are kept but flagged `verified=False`.

    When the same text occurs more than once, each quote takes the first occurrence
    not already claimed by an earlier quote, so repeated citations highlight
    different passages.
    """
    normalized_draft, index_map = normalize_with_map(draft)
    claimed: set[int] = set()
    results: list[VerifiedEvidence] = []

    for item in items:
        needle = normalize(item.quote)
        position = _find_unclaimed(normalized_draft, needle, claimed) if needle else None
        if position is None:
            results.append(VerifiedEvidence(quote=item.quote, supports=item.supports, verified=False))
            continue
        claimed.add(position)
        start = index_map[position]
        end = index_map[position + len(needle) - 1] + 1
        results.append(
            VerifiedEvidence(
                quote=draft[start:end], supports=item.supports, start=start, end=end, verified=True
            )
        )
    return results


def _find_unclaimed(haystack: str, needle: str, claimed: set[int]) -> int | None:
    first: int | None = None
    position = haystack.find(needle)
    while position != -1:
        if first is None:
            first = position
        if position not in claimed:
            return position
        position = haystack.find(needle, position + 1)
    return first  # every occurrence is claimed already; reuse the first
