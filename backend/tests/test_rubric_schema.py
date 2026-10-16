import pytest
from pydantic import ValidationError

from app.schemas.rubric import Rubric


def criterion(**overrides):
    base = {
        "id": "thesis",
        "name": "Thesis",
        "max_points": 10,
        "levels": [
            {"label": "Excellent", "points": 10, "description": "Clear and arguable"},
            {"label": "Weak", "points": 4, "description": "Vague"},
        ],
    }
    return {**base, **overrides}


def test_valid_rubric_and_total_points() -> None:
    rubric = Rubric.model_validate(
        {"criteria": [criterion(), criterion(id="style", name="Style", max_points=5,
                                             levels=[{"label": "Good", "points": 5}])]}
    )
    assert rubric.total_points == 15
    assert rubric.criteria[0].levels[0].inferred is False


def test_inferred_flag_round_trips() -> None:
    rubric = Rubric.model_validate(
        {"criteria": [criterion(levels=[{"label": "Full", "points": 10, "inferred": True}])]}
    )
    assert rubric.model_dump()["criteria"][0]["levels"][0]["inferred"] is True


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"criteria": []}, "at least 1"),
        ({"criteria": [criterion(), criterion()]}, "duplicate criterion ids"),
        ({"criteria": [criterion(levels=[])]}, "at least 1"),
        ({"criteria": [criterion(max_points=0)]}, "greater than 0"),
        ({"criteria": [criterion(id="Bad Id")]}, "pattern"),
        ({"criteria": [criterion(levels=[{"label": "A", "points": 11}])]}, "more points"),
        ({"criteria": [criterion(levels=[{"label": "A", "points": 1}, {"label": " a ", "points": 2}])]},
         "duplicate level labels"),
        ({"criteria": [criterion(levels=[{"label": "A", "points": -1}])]}, "greater than or equal"),
    ],
)
def test_invalid_rubrics_are_rejected(data: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Rubric.model_validate(data)
