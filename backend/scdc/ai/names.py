"""Match names in messages ("Maju", "chairs") to business records (S-01, R-01). No AI in this file.

Rules (agreed in v2 step 2b):
- Comparison ignores case and punctuation, and treats simple plurals as singular
  ("Chairs!" == "chair", "tables" == "table", "boxes" == "box").
- A name matches a record if it equals the record's name or an alias, or contains one as whole
  words ("Maju Rental here"), or is a whole-word part of one ("Cahaya" in "Cahaya Event Rentals").
- Two or more records match -> ambiguous, all of them suggested.
- A close spelling ("Maju Rentel", "chiars") is never matched automatically; it is only suggested.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping

MatchStatus = Literal["matched", "ambiguous", "unmatched"]

# How similar a misspelling must be (0..1) to be offered as a suggestion.
SUGGESTION_CUTOFF = 0.8


def singular(word: str) -> str:
    """Turn a simple English plural into its singular: chairs→chair, boxes→box, supplies→supply.

    Deliberately simple. It only needs to treat both sides of a comparison the same way.
    Words ending in "ss" (glass) and very short words (bus, gas) are left alone.
    """
    if len(word) <= 3 or word.endswith("ss"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "sses", "zes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def norm(text: str) -> str:
    """Normalize for comparison: lowercase, punctuation to spaces, plurals to singular."""
    words = re.sub(r"[^0-9a-z]+", " ", text.lower()).split()
    return " ".join(singular(w) for w in words)


def contains_phrase(haystack: str, needle: str) -> bool:
    """True if `needle` appears in `haystack` as whole words, after normalizing both."""
    h, n = norm(haystack), norm(needle)
    return bool(n) and f" {n} " in f" {h} "


@dataclass
class NameMatch:
    """The result of matching one name against the records."""

    status: MatchStatus
    entity_id: str | None = None
    candidates: list[str] = field(default_factory=list)  # suggestions for the owner


def resolve_name(text: str | None, names_by_id: Mapping[str, Iterable[str]]) -> NameMatch:
    """Match a name such as "Maju" or "folding chairs" to exactly one record ID.

    `names_by_id` maps each record ID to its name and aliases, e.g. {"S-01": ["Maju Rental Supplies", "Maju"]}.
    Tries, in order: exact name/alias, whole-word match, then close spellings (suggestions only).
    """
    t = norm(text or "")
    if not t:
        return NameMatch("unmatched")
    names = {eid: [norm(n) for n in ns if norm(n)] for eid, ns in names_by_id.items()}

    exact = sorted(eid for eid, ns in names.items() if t in ns)
    if len(exact) == 1:
        return NameMatch("matched", exact[0])
    if exact:
        return NameMatch("ambiguous", candidates=exact)

    partial = sorted(
        eid for eid, ns in names.items()
        if any(contains_phrase(t, n) or (len(t) >= 3 and contains_phrase(n, t)) for n in ns)
    )
    if len(partial) == 1:
        return NameMatch("matched", partial[0])
    if partial:
        return NameMatch("ambiguous", candidates=partial)

    owner_of = {n: eid for eid, ns in names.items() for n in ns}
    close = difflib.get_close_matches(t, list(owner_of), n=3, cutoff=SUGGESTION_CUTOFF)
    return NameMatch("unmatched", candidates=sorted({owner_of[c] for c in close}))


def scan_for_names(message: str, names_by_id: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """Find every record a message mentions by name or alias. Returns {record ID: the name found}.

    Used by the rule-based extractor, which has no model to tell it where the names are.
    Longer aliases are tried first, so "Maju Rental" is reported rather than just "Maju".
    """
    found: dict[str, str] = {}
    for eid, ns in names_by_id.items():
        for name in sorted(ns, key=len, reverse=True):
            if contains_phrase(message, name):
                found[eid] = name
                break
    return found
