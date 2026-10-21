"""Turn English date phrases into calendar dates. Deterministic: no AI in this file.

Used two ways in Module A:
- the rule-based extractor finds date phrases in a message with `find_date_mentions`;
- the model path uses the same function to cross-check the dates the model returned.

Rules (agreed in v2 step 2a), for a report made on Tue 2026-10-20:
    "2026-10-23", "23 Oct", "Oct 23", "23/10"   -> 2026-10-23 (numeric dates are day/month)
    "today", "tomorrow", "day after tomorrow"  -> 10-20, 10-21, 10-22
    "Friday", "this Friday"                    -> the next Friday, 10-23
    "in 3 days"                                -> 10-23
    "two days late"                            -> original date + 2, only if the original date is known
    "next Friday", a weekday equal to today    -> ambiguous (never guessed)
    "next week", "soon", "end of month" ...    -> ambiguous (never guessed)
    "5 Jan" (no year)                          -> the nearest upcoming one, 2027-01-05
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

WEEKDAYS: dict[str, int] = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
# Short names that are also ordinary words ("the sun is out", "we sat down", "they wed").
# They only count with date context: after "on/by/this/next/..." or right before a date ("Sun 25 Oct").
RISKY_WEEKDAYS = {"mon", "wed", "sat", "sun"}

MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_RE = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)

# Small number words, for phrases like "two days late" or "in three days".
NUMBER_WORDS: dict[str, int] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
NUM_RE = r"(\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"

MentionKind = Literal["iso", "day_month", "numeric", "relative", "in_days", "weekday", "offset", "vague"]
MentionStatus = Literal["exact", "needs_anchor", "ambiguous"]
ParseStatus = Literal["ok", "ambiguous", "conflicting", "needs_anchor", "unparseable"]


@dataclass
class DateMention:
    """One date phrase found in a text, and what it resolves to.

    status:
      exact        -> `value` is the date
      needs_anchor -> a delay like "two days late"; needs the original date to resolve
      ambiguous    -> a vague phrase ("next week"); never turned into a date
    """

    text: str
    start: int
    end: int
    kind: MentionKind
    status: MentionStatus
    value: date | None = None
    offset_days: int | None = None
    note: str = ""


@dataclass
class DateParse:
    """The single date a phrase means, or why there isn't one."""

    status: ParseStatus
    value: date | None = None
    note: str = ""
    mentions: list[DateMention] = field(default_factory=list)


def to_number(token: str) -> int | None:
    """Convert "3" or "three" to 3. Returns None for anything else."""
    token = token.lower()
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def _build_date(day: int, month: int, year_text: str | None, reported_on: date) -> date | None:
    """Make a date from day and month. With no year, use the nearest upcoming one. None if invalid.

    A date up to a week in the past keeps this year, so a past date in a message can still be
    detected (and flagged) instead of silently becoming next year.
    """
    try:
        if year_text:
            year = int(year_text)
            return date(year + 2000 if year < 100 else year, month, day)
        candidate = date(reported_on.year, month, day)
        if candidate < reported_on - timedelta(days=7):
            candidate = date(reported_on.year + 1, month, day)
        return candidate
    except ValueError:  # e.g. 31 Feb
        return None


def _next_weekday(reported_on: date, weekday: int) -> date:
    """The next date strictly after `reported_on` that falls on `weekday` (0 = Monday)."""
    return reported_on + timedelta(days=(weekday - reported_on.weekday()) % 7 or 7)


def _weekday_parts(match: re.Match) -> tuple[str, str]:
    """Split a weekday match into (qualifier, weekday name), e.g. "next Fri" → ("next", "fri").

    A leading word other than this/next/coming ("on", "by", ...) means no special qualifier.
    """
    words = match.group(0).lower().split()
    qualifier = words[0] if len(words) > 1 and words[0] in ("this", "next", "coming") else ""
    return qualifier, words[-1]


def _by_position(mention: DateMention) -> int:
    """Sort key: where the mention starts in the text."""
    return mention.start


def find_date_mentions(text: str, reported_on: date, anchor: date | None = None) -> list[DateMention]:
    """Find every date phrase in `text`, resolved relative to the report date.

    `anchor` is the original delivery date, used for delays like "two days late".
    Patterns are tried from most to least specific; once part of the text is claimed by
    one pattern, later patterns cannot claim it again.
    """
    mentions: list[DateMention] = []
    claimed: list[tuple[int, int]] = []

    def add(match: re.Match, kind: MentionKind, status: MentionStatus, value: date | None = None,
            offset: int | None = None, note: str = "") -> None:
        """Record a match, unless it overlaps text an earlier pattern already claimed."""
        start, end = match.span()
        if any(start < e and s < end for s, e in claimed):
            return
        claimed.append((start, end))
        mentions.append(DateMention(match.group(0), start, end, kind, status, value, offset, note))

    flags = re.IGNORECASE

    # ISO: 2026-10-23
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        try:
            add(m, "iso", "exact", date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass

    # Delays: "two days late", "2 days later", "delayed by 2 days"
    late = r"(?:late|later|delay(?:ed)?|behind)"
    for pattern in (rf"\b{NUM_RE}\s+(?:more\s+)?days?\s+{late}\b", rf"\b{late}\s+(?:by\s+|for\s+)?{NUM_RE}\s+days?\b"):
        for m in re.finditer(pattern, text, flags):
            days = to_number(m[1])
            if days is None:
                continue
            if anchor is not None:
                add(m, "offset", "exact", anchor + timedelta(days=days), days)
            else:
                add(m, "offset", "needs_anchor", None, days, "a delay was given, but the original date is unknown")

    # "in 3 days": counted from the report date
    for m in re.finditer(rf"\bin\s+{NUM_RE}\s+days?\b", text, flags):
        days = to_number(m[1])
        if days is not None:
            add(m, "in_days", "exact", reported_on + timedelta(days=days))

    # Day then month: "23 Oct", "23rd October 2026"
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTH_RE}(?:,?\s+(\d{{4}}))?\b", text, flags):
        value = _build_date(int(m[1]), MONTHS[m[2].lower()[:3]], m[3], reported_on)
        if value:
            add(m, "day_month", "exact", value)

    # Month then day: "Oct 23", "October 23rd, 2026"
    for m in re.finditer(rf"\b{MONTH_RE}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", text, flags):
        value = _build_date(int(m[2]), MONTHS[m[1].lower()[:3]], m[3], reported_on)
        if value:
            add(m, "day_month", "exact", value)

    # Numeric, day first: "23/10", "23/10/2026"
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text):
        value = _build_date(int(m[1]), int(m[2]), m[3], reported_on)
        if value:
            add(m, "numeric", "exact", value)

    # Relative words
    for m in re.finditer(r"\b(day after tomorrow|tomorrow|today|tonight)\b", text, flags):
        word = m[1].lower()
        days = 2 if word == "day after tomorrow" else 1 if word == "tomorrow" else 0
        add(m, "relative", "exact", reported_on + timedelta(days=days))

    # Weekdays: "Friday", "this Friday"; "next Friday" is ambiguous.
    # Safe names always count; risky short names ("sun") need a date word before them
    # or a date right after them.
    safe_re = "|".join(sorted(set(WEEKDAYS) - RISKY_WEEKDAYS, key=len, reverse=True))
    risky_re = "|".join(sorted(RISKY_WEEKDAYS))
    date_after = rf"(?=\.?,?\s+(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH_RE}|\d{{1,2}}/\d))"
    weekday_patterns = (
        rf"\b(?:(this|next|coming)\s+)?({safe_re})\b",
        rf"\b(?:on|by|until|till|before|this|next|coming)\s+({risky_re})\b",
        rf"\b({risky_re}){date_after}",
    )
    for pattern in weekday_patterns:
        for m in re.finditer(pattern, text, flags):
            qualifier, name = _weekday_parts(m)
            weekday = WEEKDAYS[name]
            if qualifier == "next":
                add(m, "weekday", "ambiguous", note="'next <weekday>' can mean this week or the week after")
            elif weekday == reported_on.weekday() and qualifier != "this":
                add(m, "weekday", "ambiguous", note="same weekday as the report day: today or next week?")
            elif weekday == reported_on.weekday():
                add(m, "weekday", "exact", reported_on)
            else:
                add(m, "weekday", "exact", _next_weekday(reported_on, weekday))

    # Vague timing: recorded so callers know a date was mentioned, but never resolved
    for m in re.finditer(
        r"\b(next week|end of (?:the )?(?:week|month)|soon|later|(?:a )?few days|asap|tba|tbc|not sure when)\b",
        text, flags,
    ):
        add(m, "vague", "ambiguous", note="vague timing")

    mentions.sort(key=_by_position)
    return mentions


def resolve_date_text(text: str | None, reported_on: date, anchor: date | None = None) -> DateParse:
    """Resolve a phrase to exactly one date, or say why that is not possible.

    - one date found (possibly mentioned several times) -> ok
    - two or more different dates                       -> conflicting
    - only vague phrases                                -> ambiguous
    - only a delay with no known original date          -> needs_anchor
    - nothing date-like                                 -> unparseable
    """
    if not text or not text.strip():
        return DateParse("unparseable", note="no date given")
    mentions = find_date_mentions(text, reported_on, anchor)
    found = sorted({m.value for m in mentions if m.status == "exact" and m.value})
    if len(found) > 1:
        return DateParse("conflicting", note="different dates: " + ", ".join(d.isoformat() for d in found),
                         mentions=mentions)
    if found:
        return DateParse("ok", found[0], mentions=mentions)
    ambiguous = [m for m in mentions if m.status == "ambiguous"]
    if ambiguous:
        return DateParse("ambiguous", note=f"'{ambiguous[0].text}': {ambiguous[0].note}", mentions=mentions)
    if any(m.status == "needs_anchor" for m in mentions):
        return DateParse("needs_anchor", note="a delay was given, but the original date is unknown", mentions=mentions)
    return DateParse("unparseable", note=f"no date found in '{text.strip()}'", mentions=mentions)
