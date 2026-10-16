from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Level(BaseModel):
    label: str = Field(min_length=1)
    points: float = Field(ge=0)
    description: str = ""
    # True when the parser made this level up because the rubric had none.
    inferred: bool = False


class Criterion(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_\-]*$")
    name: str = Field(min_length=1)
    max_points: float = Field(gt=0)
    levels: list[Level] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_levels(self) -> Criterion:
        labels = [level.label.strip().casefold() for level in self.levels]
        if len(set(labels)) != len(labels):
            raise ValueError(f"criterion '{self.id}' has duplicate level labels")
        too_high = [level.label for level in self.levels if level.points > self.max_points]
        if too_high:
            raise ValueError(
                f"criterion '{self.id}': levels {too_high} have more points than max_points "
                f"({self.max_points})"
            )
        return self


class Rubric(BaseModel):
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_unique_ids(self) -> Rubric:
        ids = [criterion.id for criterion in self.criteria]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate criterion ids: {duplicates}")
        return self

    @property
    def total_points(self) -> float:
        return sum(criterion.max_points for criterion in self.criteria)
