"""Checkable requirements extracted from assignment instructions.

Only requirements that plain code can verify belong here. Anything about content
quality is the rubric's job, not an instruction check.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class WordCountRequirement(BaseModel):
    type: Literal["word_count"] = "word_count"
    description: str
    min_words: int | None = Field(default=None, ge=0)
    max_words: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_bounds(self) -> WordCountRequirement:
        if self.min_words is None and self.max_words is None:
            raise ValueError("word_count needs min_words, max_words, or both")
        if None not in (self.min_words, self.max_words) and self.min_words > self.max_words:  # type: ignore[operator]
            raise ValueError("min_words cannot exceed max_words")
        return self


class RequiredSectionsRequirement(BaseModel):
    type: Literal["required_sections"] = "required_sections"
    description: str
    headings: list[str] = Field(min_length=1)


class MinCitationsRequirement(BaseModel):
    type: Literal["min_citations"] = "min_citations"
    description: str
    count: int = Field(ge=1)


class CitationStyleRequirement(BaseModel):
    type: Literal["citation_style"] = "citation_style"
    description: str
    style: Literal["APA", "MLA", "IEEE", "Harvard"]


Requirement = Annotated[
    WordCountRequirement
    | RequiredSectionsRequirement
    | MinCitationsRequirement
    | CitationStyleRequirement,
    Field(discriminator="type"),
]


class RequirementList(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)


class CheckResult(BaseModel):
    requirement: Requirement
    passed: bool
    details: str
