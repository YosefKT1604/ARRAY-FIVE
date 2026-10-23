"""Find quantities like "20 chairs" in a message. No AI in this file.

Rules (agreed in v2 step 2b):
- A quantity is a number next to an item or unit word: "20 chairs", "20 folding chairs",
  "twenty chairs", "20 pcs". A bare "20", "Order #4521" or "RM 80" is not a quantity.
- With several quantities, a number after "remaining / the rest / balance / outstanding / another"
  is the affected one. Otherwise, if the numbers differ, nothing is chosen: they become
  suggestions for the owner. A single distinct number is used.
- "15 of the 40 chairs" yields both 15 and 40, so the owner decides (the code never subtracts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .names import norm, singular

UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}

_tens_re = "|".join(TENS)
_simple_re = "|".join(sorted([*UNITS, *TEENS, *TENS, "hundred"], key=len, reverse=True))
# Digits, "twenty-five" / "twenty five", or a single number word.
NUMBER_RE = rf"(\d+|(?:{_tens_re})[\s-](?:{'|'.join(UNITS)})|{_simple_re})"

GENERIC_UNITS = ("unit", "pc", "pcs", "piece", "no", "nos", "set", "box", "pack", "lot")
REMAINING_CUES = ("remaining", "the rest", "rest of", "balance", "outstanding", "another", "the other")

ChoiceStatus = Literal["ok", "conflicting", "missing"]


def parse_number(text: str) -> int | None:
    """Convert "20", "twenty" or "twenty-five" to an int. None if it is not a number."""
    t = text.strip().lower().replace("-", " ")
    if t.isdigit():
        return int(t)
    parts = t.split()
    if len(parts) == 2 and parts[0] in TENS and parts[1] in UNITS:
        return TENS[parts[0]] + UNITS[parts[1]]
    if len(parts) == 1:
        word = parts[0]
        return UNITS.get(word) or TEENS.get(word) or TENS.get(word) or (100 if word == "hundred" else None)
    return None


@dataclass
class QuantityMention:
    """A number in the message that is attached to an item or unit word."""

    value: int
    text: str
    start: int
    remaining_cue: bool  # True if introduced by "remaining", "the rest", ...: the late part


@dataclass
class QuantityChoice:
    """Which quantity the message says is affected, or why none was chosen."""

    status: ChoiceStatus
    value: int | None = None
    text: str | None = None
    candidates: list[int] = field(default_factory=list)  # suggestions for the owner
    note: str = ""


def _item_pattern(item_words: Iterable[str]) -> str:
    """Regex alternation for item/unit words, each allowing a plural ending (chair, chairs, boxes)."""
    words = {singular(w) for phrase in [*item_words, *GENERIC_UNITS] for w in [norm(phrase)] if w}
    escaped = sorted((re.escape(w).replace(r"\ ", r"\s+") for w in words), key=len, reverse=True)
    return rf"(?:{'|'.join(escaped)})(?:e?s)?"


def find_quantity_mentions(message: str, item_words: Iterable[str]) -> list[QuantityMention]:
    """Find every number followed (within two words) by one of `item_words` or a generic unit.

    `item_words` are the names and aliases of the resources the message may be about.
    """
    item = _item_pattern(item_words)
    found: dict[int, QuantityMention] = {}

    def record(value_text: str, start: int, whole: str) -> None:
        """Store a mention, checking the 25 characters before it for a "remaining" cue."""
        value = parse_number(value_text)
        if value is None or value < 1 or start in found:
            return
        before = message[max(0, start - 25):start]
        cue = any(contains_cue(before, c) for c in REMAINING_CUES)
        found[start] = QuantityMention(value, whole, start, cue)

    # "15 of the 40 chairs": both numbers are mentions; the owner decides which is affected.
    for m in re.finditer(rf"\b{NUMBER_RE}\s+(?:out\s+)?of\s+(?:the\s+)?{NUMBER_RE}\s+(?:[a-z]+\s+)?{item}\b",
                         message, re.IGNORECASE):
        record(m[1], m.start(1), m.group(0))
        record(m[2], m.start(2), m.group(0)[m.start(2) - m.start():])
    # "20 chairs", "20 folding chairs", "twenty-five pcs"
    for m in re.finditer(rf"\b{NUMBER_RE}\s+(?:[a-z]+\s+){{0,2}}?{item}\b", message, re.IGNORECASE):
        record(m[1], m.start(1), m.group(0))
    return sorted(found.values(), key=_by_start)


def _by_start(mention: QuantityMention) -> int:
    """Sort key: where the mention starts in the message."""
    return mention.start


def contains_cue(text: str, cue: str) -> bool:
    """True if a "remaining"-type cue appears in `text` as whole words."""
    return re.search(rf"\b{re.escape(cue)}\b", text, re.IGNORECASE) is not None


def choose_affected_quantity(mentions: list[QuantityMention]) -> QuantityChoice:
    """Pick the affected quantity: a 'remaining' number, else the only distinct number, else ask the owner."""
    if not mentions:
        return QuantityChoice("missing", note="the message does not state a quantity")
    cued = {m.value: m for m in mentions if m.remaining_cue}
    pool = cued or {m.value: m for m in mentions}
    if len(pool) == 1:
        value, mention = next(iter(pool.items()))
        return QuantityChoice("ok", value, mention.text)
    values = sorted(pool)
    return QuantityChoice("conflicting", candidates=values,
                          note="the message gives different quantities: " + ", ".join(map(str, values)))


def number_in_text(value: int, text: str) -> bool:
    """True if `value` is written anywhere in `text`, as digits or words ("20", "twenty").

    Used to check a model's quantity: a number the message never states is not trusted.
    """
    return any(parse_number(tok) == value for tok in re.findall(NUMBER_RE, text, re.IGNORECASE))
