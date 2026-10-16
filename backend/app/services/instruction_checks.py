"""Deterministic evaluation of instruction requirements. No LLM calls in this module.

Known limits (kept simple on purpose):
- Citations are counted from in-text patterns only; the reference list is not parsed.
- Headings are detected line by line: markdown "#" headings, or short standalone lines,
  optionally numbered, bold, or ending with a colon.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.schemas.requirements import (
    CheckResult,
    CitationStyleRequirement,
    MinCitationsRequirement,
    RequiredSectionsRequirement,
    Requirement,
    WordCountRequirement,
)

# --- word count -----------------------------------------------------------------

_WORD_RE = re.compile(r"\w+(?:['’\-]\w+)*")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _check_word_count(req: WordCountRequirement, draft: str) -> CheckResult:
    words = count_words(draft)
    problems = []
    if req.min_words is not None and words < req.min_words:
        problems.append(f"{req.min_words - words} words short of the {req.min_words}-word minimum")
    if req.max_words is not None and words > req.max_words:
        problems.append(f"{words - req.max_words} words over the {req.max_words}-word maximum")
    details = f"Draft has {words} words."
    if problems:
        details += " " + "; ".join(problems) + "."
    return CheckResult(requirement=req, passed=not problems, details=details)


# --- headings -------------------------------------------------------------------

_NUMBERING_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?|[ivxlc]+[.)])\s+", re.IGNORECASE)
_MAX_HEADING_CHARS = 100


def _normalize_heading(line: str) -> str:
    text = line.strip().lstrip("#").strip()
    text = text.strip("*_ ").rstrip(":").strip("*_ ")
    text = _NUMBERING_RE.sub("", text)
    return re.sub(r"\s+", " ", text).casefold()


def find_headings(draft: str) -> set[str]:
    """Normalized text of every line that could be a heading."""
    found = set()
    for line in draft.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) <= _MAX_HEADING_CHARS:
            found.add(_normalize_heading(stripped))
    return found


def _check_sections(req: RequiredSectionsRequirement, draft: str) -> CheckResult:
    present = find_headings(draft)
    missing = [h for h in req.headings if _normalize_heading(h) not in present]
    if missing:
        details = "Missing section(s): " + ", ".join(missing) + "."
    else:
        details = "All required sections found: " + ", ".join(req.headings) + "."
    return CheckResult(requirement=req, passed=not missing, details=details)


# --- citations ------------------------------------------------------------------

_AUTHOR = r"[A-Z][A-Za-z'’\-]+"
_AUTHORS = rf"{_AUTHOR}(?:[ ,]+(?:{_AUTHOR}|and|&|et al\.?|of)){{0,6}}"
_YEAR = r"(?:19|20)\d{2}[a-z]?"
_PREFIX = r"(?:(?:see|e\.g\.,?|cf\.|also)\s+)?"
_PAREN_RE = re.compile(r"\(([^()]{3,300})\)")

_AUTHOR_YEAR_COMMA = re.compile(rf"{_PREFIX}{_AUTHORS},\s*{_YEAR}(?:,\s*[^()]*)?", re.IGNORECASE)
_AUTHOR_YEAR_PLAIN = re.compile(rf"{_PREFIX}{_AUTHORS}\s+{_YEAR}(?:,\s*[^()]*)?", re.IGNORECASE)
# Page numbers are 1-3 digits, so a 4-digit year is never mistaken for a page.
_AUTHOR_PAGE = re.compile(rf"{_PREFIX}{_AUTHORS}\s+\d{{1,3}}(?:\s*[-–]\s*\d{{1,3}})?", re.IGNORECASE)
_NARRATIVE = re.compile(
    rf"\b({_AUTHOR}(?: et al\.|\s(?:and|&)\s{_AUTHOR})?)\s\(({_YEAR})\)"
)
_NUMERIC = re.compile(r"\[(\d+(?:\s*[,–\-]\s*\d+)*)\]")

# Citation "forms" found in text, and which required styles accept each.
_FORMS = ("author_year_comma", "author_year_plain", "narrative", "author_page", "numeric")
_STYLE_FORMS: dict[str, set[str]] = {
    "APA": {"author_year_comma", "narrative"},
    "Harvard": {"author_year_comma", "author_year_plain", "narrative"},
    "MLA": {"author_page"},
    "IEEE": {"numeric"},
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _expand_numeric(group: str) -> set[str]:
    numbers: set[str] = set()
    for part in re.split(r"\s*,\s*", group):
        bounds = re.split(r"\s*[–\-]\s*", part)
        if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
            low, high = int(bounds[0]), int(bounds[1])
            if low <= high and high - low < 100:
                numbers.update(f"[{n}]" for n in range(low, high + 1))
                continue
        numbers.update(f"[{b}]" for b in bounds if b.isdigit())
    return numbers


def find_citations(text: str) -> dict[str, set[str]]:
    """Distinct in-text citations found, grouped by form."""
    found: dict[str, set[str]] = {form: set() for form in _FORMS}
    for paren in _PAREN_RE.finditer(text):
        for segment in paren.group(1).split(";"):
            segment = segment.strip()
            if _AUTHOR_YEAR_COMMA.fullmatch(segment):
                found["author_year_comma"].add(_norm(segment))
            elif _AUTHOR_YEAR_PLAIN.fullmatch(segment):
                found["author_year_plain"].add(_norm(segment))
            elif _AUTHOR_PAGE.fullmatch(segment):
                found["author_page"].add(_norm(segment))
    for match in _NARRATIVE.finditer(text):
        found["narrative"].add(_norm(f"{match.group(1)} {match.group(2)}"))
    for match in _NUMERIC.finditer(text):
        found["numeric"].update(_expand_numeric(match.group(1)))
    return found


def _check_min_citations(req: MinCitationsRequirement, draft: str) -> CheckResult:
    total = sum(len(keys) for keys in find_citations(draft).values())
    passed = total >= req.count
    details = f"Found {total} distinct in-text citation(s); {req.count} required."
    return CheckResult(requirement=req, passed=passed, details=details)


def _check_citation_style(req: CitationStyleRequirement, draft: str) -> CheckResult:
    found = find_citations(draft)
    accepted = _STYLE_FORMS[req.style]
    matching = sum(len(found[form]) for form in accepted)
    others = {form: len(found[form]) for form in _FORMS if form not in accepted and found[form]}
    if matching == 0:
        return CheckResult(
            requirement=req, passed=False,
            details=f"No in-text citations in {req.style} format were found.",
        )
    if sum(others.values()) > matching:
        return CheckResult(
            requirement=req, passed=False,
            details=(
                f"Found {matching} {req.style}-style citation(s) but more in other formats "
                f"({_describe(others)}). Use one style consistently."
            ),
        )
    return CheckResult(
        requirement=req, passed=True,
        details=f"Found {matching} in-text citation(s) in {req.style} format.",
    )


def _describe(counts: dict[str, int]) -> str:
    return ", ".join(f"{n} {form.replace('_', ' ')}" for form, n in counts.items())


# --- entry point ----------------------------------------------------------------


def evaluate_requirements(requirements: Iterable[Requirement], draft: str) -> list[CheckResult]:
    results = []
    for req in requirements:
        if isinstance(req, WordCountRequirement):
            results.append(_check_word_count(req, draft))
        elif isinstance(req, RequiredSectionsRequirement):
            results.append(_check_sections(req, draft))
        elif isinstance(req, MinCitationsRequirement):
            results.append(_check_min_citations(req, draft))
        elif isinstance(req, CitationStyleRequirement):
            results.append(_check_citation_style(req, draft))
    return results
