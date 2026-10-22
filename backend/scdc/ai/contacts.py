"""Who sent a message: match the sender's contact details to a supplier. No AI in this file.

Three clues, agreed in v2 (WhatsApp contact step):
    contact reference   exactly equal to a supplier's `contact_reference` (ignoring case)
    phone number        equal to a supplier's `phone` after normalising: "+60 12-345 6789",
                        "012-345 6789" and "60123456789" are the same number (Malaysia by default)
    saved contact name  the name the owner saved for the number ("Ali Maju Rental"), matched against
                        supplier names and aliases like a name in a message (exact, alias, whole word);
                        a close spelling is only a suggestion
If the clues point to one supplier, it identifies the sender. If they point to different suppliers,
that is a conflict and the owner decides. Combining this with what the message says is done in combine.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .names import resolve_name
from .schemas import BusinessSnapshot

DEFAULT_COUNTRY_CODE = "60"  # Malaysia: a number starting with 0 is a local number


@dataclass
class SenderMatch:
    """What the sender's contact details say about the supplier.

    `supplier_id` is set when the clues agree on one supplier; `conflict` lists the suppliers when they
    disagree; `suggestions` are possible suppliers from a close (not exact) name.
    """

    supplier_id: str | None = None
    label: str = ""                                   # where it came from, for the evidence text
    conflict: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def normalise_phone(number: str | None) -> str | None:
    """A phone number as digits with the country code ("012-345 6789" -> "60123456789"); None if not a number."""
    if not number:
        return None
    digits = re.sub(r"\D", "", number)
    if len(digits) < 8:
        return None
    if number.strip().startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    if digits.startswith("0"):
        return DEFAULT_COUNTRY_CODE + digits[1:]
    return digits


def identify_sender(
    snapshot: BusinessSnapshot,
    *,
    contact_reference: str | None = None,
    phone: str | None = None,
    contact_name: str | None = None,
) -> SenderMatch | None:
    """Match the sender's contact reference, phone and saved name to suppliers. None if no clue was given."""
    if not (contact_reference or phone or contact_name):
        return None
    found: dict[str, list[str]] = {}  # supplier ID -> the clues pointing to it
    suggestions: list[str] = []

    if contact_reference:
        wanted = contact_reference.strip().lower()
        hits = [s.id for s in snapshot.suppliers if s.contact_reference and s.contact_reference.strip().lower() == wanted]
        if len(hits) == 1:
            found.setdefault(hits[0], []).append(f"sender contact {contact_reference}")

    number = normalise_phone(phone)
    if number:
        hits = [s.id for s in snapshot.suppliers if normalise_phone(s.phone) == number]
        if len(hits) == 1:
            found.setdefault(hits[0], []).append(f"sender phone +{number}")

    if contact_name:
        match = resolve_name(contact_name, {s.id: [s.name, *s.aliases] for s in snapshot.suppliers})
        if match.status == "matched":
            found.setdefault(match.entity_id, []).append(f"saved contact name '{contact_name}'")
        else:
            suggestions = list(match.candidates)

    if len(found) > 1:
        return SenderMatch(conflict=sorted(found), label="; ".join(c for clues in found.values() for c in clues))
    if found:
        supplier_id, clues = next(iter(found.items()))
        return SenderMatch(supplier_id=supplier_id, label=" and ".join(clues))
    return SenderMatch(suggestions=suggestions) if suggestions else None
