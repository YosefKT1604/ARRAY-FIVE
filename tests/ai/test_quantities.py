"""Tests for quantity finding: one block per rule agreed in step 2b."""

from __future__ import annotations

import pytest

from scdc.ai.quantities import choose_affected_quantity, find_quantity_mentions, number_in_text, parse_number

CHAIR_WORDS = ["Folding Chairs", "chairs", "chair"]


@pytest.mark.parametrize("text, expected", [
    ("20", 20), ("twenty", 20), ("twenty-five", 25), ("twenty five", 25), ("fifteen", 15), ("chairs", None),
])
def test_parse_number(text, expected):
    """Digits, number words and compounds become ints; other words do not."""
    assert parse_number(text) == expected


@pytest.mark.parametrize("message, values", [
    ("We send 20 chairs tomorrow", [20]),
    ("20 folding chairs are late", [20]),
    ("twenty chairs are late", [20]),
    ("twenty-five chairs are late", [25]),
    ("the 20 pcs are late", [20]),
    ("Order #4521 is late, RM 80 refund", []),      # not next to an item word
    ("We send 20 tomorrow", []),                     # bare number
])
def test_only_numbers_next_to_item_words_count(message, values):
    """Numbers count only when an item or unit word follows within two words."""
    assert [m.value for m in find_quantity_mentions(message, CHAIR_WORDS)] == values


def test_demo_message_picks_the_remaining_quantity():
    """'send 20 chairs tomorrow, the remaining 20 chairs on Friday' → 20, from the 'remaining' part."""
    message = ("Boss, sorry ya. Our chair delivery for tomorrow will be late. We can only send 20 chairs "
               "tomorrow, the remaining 20 chairs we deliver on Friday.")
    choice = choose_affected_quantity(find_quantity_mentions(message, CHAIR_WORDS))
    assert choice.status == "ok" and choice.value == 20 and "remaining" not in choice.text


def test_remaining_cue_wins_over_other_numbers():
    """With 15 sent now and the remaining 25 later, the affected quantity is 25."""
    message = "We send 15 chairs today, the remaining 25 chairs on Friday."
    choice = choose_affected_quantity(find_quantity_mentions(message, CHAIR_WORDS))
    assert choice.status == "ok" and choice.value == 25


def test_different_numbers_without_cue_go_to_the_owner():
    """'20 chairs ... correction, 30 chairs' → nothing chosen; 20 and 30 suggested."""
    message = "20 chairs will be late. Sorry correction, 30 chairs will be late."
    choice = choose_affected_quantity(find_quantity_mentions(message, CHAIR_WORDS))
    assert choice.status == "conflicting" and choice.value is None and choice.candidates == [20, 30]


def test_part_of_total_is_not_subtracted():
    """'only 15 of the 40 chairs' gives 15 and 40 as suggestions; the code never computes 25."""
    choice = choose_affected_quantity(find_quantity_mentions("Only 15 of the 40 chairs come tomorrow.", CHAIR_WORDS))
    assert choice.status == "conflicting" and choice.candidates == [15, 40]


def test_no_quantity_is_missing():
    """'the remaining chairs' has no number, so the quantity is missing (never guessed)."""
    choice = choose_affected_quantity(find_quantity_mentions("We deliver the remaining chairs on Friday.", CHAIR_WORDS))
    assert choice.status == "missing" and choice.value is None


def test_plural_item_words_match_without_both_forms():
    """'tent' as the only item word still matches '10 tents'."""
    assert [m.value for m in find_quantity_mentions("The 10 tents are late", ["tent"])] == [10]


@pytest.mark.parametrize("value, text, expected", [
    (20, "the remaining 20 chairs", True),
    (20, "twenty chairs", True),
    (40, "chair delivery will be late, we deliver on Friday", False),
    (2, "the 20 chairs", False),                    # 2 is not 20
])
def test_number_in_text(value, text, expected):
    """A model's quantity is only trusted if the message actually states it."""
    assert number_in_text(value, text) is expected
