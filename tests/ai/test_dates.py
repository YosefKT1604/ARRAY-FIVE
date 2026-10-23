"""Tests for the date helpers: one test per rule agreed in step 2a."""

from __future__ import annotations

from datetime import date

import pytest

from scdc.ai.dates import find_date_mentions, resolve_date_text

TUE = date(2026, 10, 20)  # the demo's report day
DUE = date(2026, 10, 21)  # the demo delivery's original date


@pytest.mark.parametrize("text, expected", [
    ("2026-10-23", "2026-10-23"),
    ("23 Oct", "2026-10-23"),
    ("23rd October 2026", "2026-10-23"),
    ("Oct 23", "2026-10-23"),
    ("23/10", "2026-10-23"),
    ("23/10/2026", "2026-10-23"),
    ("today", "2026-10-20"),
    ("tomorrow", "2026-10-21"),
    ("day after tomorrow", "2026-10-22"),
    ("Friday", "2026-10-23"),
    ("this Friday", "2026-10-23"),
    ("fri", "2026-10-23"),
    ("in 3 days", "2026-10-23"),
    ("in three days", "2026-10-23"),
    ("5 Jan", "2027-01-05"),
])
def test_exact_phrases(text, expected):
    """Each agreed phrase resolves to the agreed date."""
    parsed = resolve_date_text(text, TUE)
    assert parsed.status == "ok"
    assert parsed.value.isoformat() == expected


@pytest.mark.parametrize("text", ["next Friday", "Tuesday", "next week", "soon", "end of the month", "TBC"])
def test_ambiguous_phrases_are_never_guessed(text):
    """Vague phrases, 'next <weekday>' and today's weekday give no date."""
    parsed = resolve_date_text(text, TUE)
    assert parsed.status == "ambiguous"
    assert parsed.value is None


@pytest.mark.parametrize("text", [
    "the sun is out", "we sat down to check", "they will wed in June", "mon, chairs late ya", "Sun is shining",
])
def test_short_weekday_names_that_are_ordinary_words_are_ignored(text):
    """'sun', 'sat', 'wed', 'mon' without date context are not dates."""
    assert find_date_mentions(text, TUE) == []


@pytest.mark.parametrize("text, expected", [
    ("delivery on Sun", "2026-10-25"),
    ("by sat", "2026-10-24"),
    ("this Wed", "2026-10-21"),
    ("Sun 25 Oct", "2026-10-25"),
    ("Sat, 24/10", "2026-10-24"),
    ("Fri", "2026-10-23"),
])
def test_short_weekday_names_with_date_context_count(text, expected):
    """With a date word before them or a date after them, short names are weekdays."""
    assert resolve_date_text(text, TUE).value.isoformat() == expected


def test_next_short_weekday_is_still_ambiguous():
    """'next Sat' follows the same rule as 'next Saturday'."""
    assert resolve_date_text("next Sat", TUE).status == "ambiguous"


def test_this_tuesday_on_a_tuesday_is_today():
    """'this' removes the doubt when the weekday is the report day."""
    assert resolve_date_text("this Tuesday", TUE).value == TUE


@pytest.mark.parametrize("text", ["two days late", "2 days later", "delayed by 2 days"])
def test_delay_needs_the_original_date(text):
    """A delay resolves only when the original date (the anchor) is known."""
    assert resolve_date_text(text, TUE).status == "needs_anchor"
    parsed = resolve_date_text(text, TUE, anchor=DUE)
    assert parsed.status == "ok" and parsed.value == date(2026, 10, 23)


def test_two_different_dates_conflict():
    """'three days late' (24 Oct) and 'Friday' (23 Oct) disagree, so neither is chosen."""
    parsed = resolve_date_text("three days late, on Friday", TUE, anchor=DUE)
    assert parsed.status == "conflicting"
    assert parsed.value is None


def test_same_date_twice_is_fine():
    """'two days late' and 'Friday' both mean 23 Oct, so the result is 23 Oct."""
    parsed = resolve_date_text("two days late, on Friday", TUE, anchor=DUE)
    assert parsed.status == "ok" and parsed.value == date(2026, 10, 23)


@pytest.mark.parametrize("text", ["", None, "the chairs will be late", "31/02", "RM 4.00"])
def test_no_date(text):
    """Text without a valid date is unparseable (impossible dates and prices are not dates)."""
    assert resolve_date_text(text, TUE).status == "unparseable"


def test_find_mentions_in_the_demo_message():
    """The demo message mentions tomorrow twice and Friday once, in order."""
    message = ("Boss, sorry ya. Our chair delivery for tomorrow will be late. We can only send 20 chairs "
               "tomorrow, the remaining 20 chairs we deliver on Friday.")
    found = [(m.text, m.value.isoformat()) for m in find_date_mentions(message, TUE)]
    assert found == [("tomorrow", "2026-10-21"), ("tomorrow", "2026-10-21"), ("Friday", "2026-10-23")]


def test_recent_past_date_keeps_this_year():
    """A date a few days ago stays in this year, so a 'new date in the past' can be flagged later."""
    assert resolve_date_text("18 Oct", TUE).value == date(2026, 10, 18)
