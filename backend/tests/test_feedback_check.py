import pytest

from app.schemas.grading import VerifiedEvidence
from app.schemas.rubric import Criterion
from app.services.feedback import fallback_feedback, find_drafted_content, top_fixes

DRAFT = "Social media harms sleep " + " ".join(f"w{i}" for i in range(40)) + " and that is all."


def words(n: int, prefix: str = "invented") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_long_quote_not_in_draft_is_flagged() -> None:
    text = f'Try writing: "{words(30)}"'
    assert find_drafted_content([text], DRAFT) == [words(30)]


def test_threshold_is_more_than_25_words() -> None:
    assert find_drafted_content([f'"{words(25)}"'], DRAFT) == []
    assert len(find_drafted_content([f'"{words(26)}"'], DRAFT)) == 1
    assert find_drafted_content([f'"{words(30)}"'], DRAFT, max_words=40) == []


def test_long_quote_from_the_students_own_draft_is_fine() -> None:
    own = " ".join(f"w{i}" for i in range(30))
    assert find_drafted_content([f'You wrote "{own}" here.'], DRAFT) == []


def test_own_draft_quote_matches_despite_whitespace_and_curly_quotes() -> None:
    own = "Social media harms sleep   w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13 w14 w15 w16 w17 w18 w19 w20 w21 w22 w23 w24"
    assert find_drafted_content([f"“{own}”"], DRAFT) == []


def test_curly_quoted_drafted_text_is_flagged() -> None:
    assert len(find_drafted_content([f"“{words(30)}”"], DRAFT)) == 1


def test_short_quotes_and_plain_prose_are_ignored() -> None:
    assert find_drafted_content(['Your phrase "late at night" is vague.', words(80)], DRAFT) == []


def test_blockquote_and_code_fence_are_checked() -> None:
    assert len(find_drafted_content([f"Consider:\n> {words(30)}"], DRAFT)) == 1
    assert len(find_drafted_content([f"```\n{words(30)}\n```"], DRAFT)) == 1


def test_every_text_field_is_scanned_and_all_offenders_returned() -> None:
    texts = [f'"{words(30)}"', "fine", f'"{words(27, "other")}"']
    assert len(find_drafted_content(texts, DRAFT)) == 2


CRITERION = Criterion(
    id="thesis", name="Thesis", max_points=10,
    levels=[
        {"label": "Excellent", "points": 10, "description": "Clear, arguable thesis"},
        {"label": "Fair", "points": 5, "description": "Vague thesis"},
        {"label": "Weak", "points": 0, "description": ""},
    ],
)


def test_fallback_uses_the_next_level_up_and_contains_no_drafted_text() -> None:
    fb = fallback_feedback(CRITERION, 0)
    assert fb.is_fallback and "Fair" in fb.whats_missing and "Vague thesis" in fb.whats_missing
    assert 1 <= len(fb.guiding_questions) <= 2
    top = fallback_feedback(CRITERION, 10)
    assert "Excellent" in top.whats_missing


def test_top_fixes_rank_by_points_at_stake_and_cap_at_three() -> None:
    def crit(cid: str, max_points: float) -> Criterion:
        return Criterion(id=cid, name=cid.upper(), max_points=max_points,
                         levels=[{"label": "x", "points": max_points}])

    results = [
        (crit("a", 10), 9, None),    # 1 at stake
        (crit("b", 10), 4, None),    # 6
        (crit("c", 5), 5, None),     # full marks: excluded
        (crit("d", 20), 15, None),   # 5
        (crit("e", 10), 7, None),    # 3
    ]
    fixes = top_fixes(results)
    assert [f.criterion_id for f in fixes] == ["b", "d", "e"]
    assert [f.points_at_stake for f in fixes] == [6, 5, 3]


def test_verified_evidence_model_defaults() -> None:
    assert VerifiedEvidence(quote="q", supports="met", verified=False).start is None


@pytest.mark.parametrize("n", [0, 1])
def test_top_fixes_handles_few_or_no_losses(n: int) -> None:
    crit = Criterion(id="a", name="A", max_points=5, levels=[{"label": "x", "points": 5}])
    assert len(top_fixes([(crit, 5 - n, None)])) == n
