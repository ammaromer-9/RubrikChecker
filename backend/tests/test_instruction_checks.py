import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.requirements import (
    CitationStyleRequirement,
    MinCitationsRequirement,
    RequiredSectionsRequirement,
    Requirement,
    RequirementList,
    WordCountRequirement,
)
from app.services.instruction_checks import (
    count_words,
    evaluate_requirements,
    find_citations,
    find_headings,
)


def run(req, draft: str):
    (result,) = evaluate_requirements([req], draft)
    return result


# --- word count ---

def test_count_words_handles_punctuation_hyphens_and_apostrophes() -> None:
    assert count_words("It's a well-known fact, isn't it? Yes!") == 7
    assert count_words("") == 0
    assert count_words("  \n\t ") == 0


def test_word_count_range() -> None:
    req = WordCountRequirement(description="d", min_words=3, max_words=5)
    assert run(req, "one two three").passed
    assert run(req, "one two three four five").passed
    short = run(req, "one two")
    assert not short.passed and "1 words short" in short.details
    long = run(req, "a b c d e f g")
    assert not long.passed and "2 words over" in long.details


def test_word_count_needs_a_bound() -> None:
    with pytest.raises(ValidationError):
        WordCountRequirement(description="d")
    with pytest.raises(ValidationError):
        WordCountRequirement(description="d", min_words=10, max_words=5)


# --- headings ---

HEADED = """# Introduction
Text here.

2. Methods
More text.

**Conclusion:**
End.
"""


def test_headings_in_various_formats() -> None:
    req = RequiredSectionsRequirement(
        description="d", headings=["introduction", "Methods", "Conclusion"]
    )
    assert run(req, HEADED).passed


def test_missing_heading_is_reported() -> None:
    req = RequiredSectionsRequirement(description="d", headings=["Introduction", "References"])
    result = run(req, HEADED)
    assert not result.passed
    assert "References" in result.details and "Introduction" not in result.details.split(":")[1]


def test_long_sentence_is_not_a_heading() -> None:
    draft = "Introduction to the topic is something I will write about in this very long paragraph " \
            "that goes on for a while and certainly exceeds the heading length limit of one hundred characters."
    assert "introduction" not in find_headings(draft)


# --- citations ---

APA_TEXT = (
    "Sleep matters (Walker, 2017). Others agree (Smith & Jones, 2020, p. 4; Lee et al., 2019). "
    "Brown (2018) disagrees. Repeat (Walker, 2017)."
)


def test_apa_citations_are_counted_distinctly() -> None:
    found = find_citations(APA_TEXT)
    assert len(found["author_year_comma"]) == 3  # Walker counted once
    assert len(found["narrative"]) == 1
    req = MinCitationsRequirement(description="d", count=4)
    assert run(req, APA_TEXT).passed
    assert not run(MinCitationsRequirement(description="d", count=5), APA_TEXT).passed


def test_numeric_citations_expand_ranges() -> None:
    text = "Shown before [1], [2, 4] and also [6-8]."
    assert find_citations(text)["numeric"] == {"[1]", "[2]", "[4]", "[6]", "[7]", "[8]"}


def test_mla_page_numbers_are_not_confused_with_years() -> None:
    found = find_citations("As argued (Smith 45) and (Jones 2020).")
    assert found["author_page"] == {"smith 45"}
    assert found["author_year_plain"] == {"jones 2020"}


def test_no_citations() -> None:
    result = run(MinCitationsRequirement(description="d", count=1), "Plain text (with brackets).")
    assert not result.passed and "Found 0" in result.details


@pytest.mark.parametrize(
    ("style", "text", "passed"),
    [
        ("APA", APA_TEXT, True),
        ("Harvard", "Sleep (Walker 2017) and (Smith, 2020).", True),
        ("MLA", "As argued (Smith 45) and (Jones 12-14).", True),
        ("IEEE", "As shown [1], [2].", True),
        ("APA", "As shown [1], [2].", False),
        ("MLA", "No citations here.", False),
        # Mixed styles: majority in another format fails.
        ("APA", "One (Walker, 2017). Then [1], [2], [3].", False),
    ],
)
def test_citation_style(style: str, text: str, passed: bool) -> None:
    result = run(CitationStyleRequirement(description="d", style=style), text)
    assert result.passed is passed, result.details


# --- schema plumbing ---

def test_requirements_parse_by_type_discriminator() -> None:
    parsed = RequirementList.model_validate(
        {"requirements": [
            {"type": "word_count", "description": "d", "min_words": 5},
            {"type": "citation_style", "description": "d", "style": "MLA"},
        ]}
    )
    assert isinstance(parsed.requirements[0], WordCountRequirement)
    assert isinstance(parsed.requirements[1], CitationStyleRequirement)
    with pytest.raises(ValidationError):
        TypeAdapter(Requirement).validate_python({"type": "tone", "description": "formal"})
    with pytest.raises(ValidationError):
        CitationStyleRequirement(description="d", style="Chicago")  # type: ignore[arg-type]
