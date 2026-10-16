from app.schemas.grading import EvidenceQuote
from app.services.evidence import contains_text, normalize_with_map, verify_evidence

DRAFT = "Sleep matters.\nStudents scroll   late at night.\n\nSchools   should   act."


def verify(*quotes: str, draft: str = DRAFT):
    return verify_evidence(draft, [EvidenceQuote(quote=q, supports="met") for q in quotes])


def test_exact_quote_gets_offsets_into_the_original_text() -> None:
    (item,) = verify("Sleep matters.")
    assert item.verified and (item.start, item.end) == (0, 14)
    assert DRAFT[item.start:item.end] == "Sleep matters."


def test_whitespace_differences_are_ignored_and_offsets_cover_the_original_span() -> None:
    (item,) = verify("Students scroll late at night.")
    assert item.verified
    assert DRAFT[item.start:item.end] == "Students scroll   late at night."
    assert item.quote == "Students scroll   late at night."


def test_quote_spanning_a_paragraph_break() -> None:
    (item,) = verify("night. Schools should act.")
    assert item.verified
    assert DRAFT[item.start:item.end].startswith("night.")
    assert DRAFT[item.start:item.end].endswith("act.")


def test_leading_and_trailing_whitespace_in_the_quote_is_ignored() -> None:
    (item,) = verify("  Sleep matters.\n ")
    assert item.verified and (item.start, item.end) == (0, 14)


def test_curly_quotes_match_straight_quotes() -> None:
    draft = "She said “stay up” and it’s fine."
    (item,) = verify('said "stay up" and it\'s fine', draft=draft)
    assert item.verified
    assert draft[item.start:item.end] == "said “stay up” and it’s fine"


def test_fabricated_or_altered_quotes_are_flagged_not_dropped() -> None:
    items = verify("Students rarely sleep.", "sleep matters.")  # invented, wrong case
    assert [i.verified for i in items] == [False, False]
    assert items[0].start is None and items[0].quote == "Students rarely sleep."


def test_empty_quote_is_not_verified() -> None:
    (item,) = verify("   ")
    assert not item.verified


def test_repeated_text_gets_distinct_occurrences() -> None:
    draft = "Sleep is key. Other words. Sleep is key."
    first, second, third = verify("Sleep is key.", "Sleep is key.", "Sleep is key.", draft=draft)
    assert (first.start, second.start) == (0, 27)
    assert third.start == 0  # every occurrence claimed: reuse the first


def test_normalize_map_points_back_into_the_original() -> None:
    normalized, index_map = normalize_with_map("a  b\n\nc")
    assert normalized == "a b c"
    assert index_map == [0, 1, 3, 4, 6]


def test_contains_text() -> None:
    assert contains_text(DRAFT, "scroll late at night")
    assert not contains_text(DRAFT, "scroll early")
    assert not contains_text(DRAFT, "   ")
