"""Rule-based extraction: the fallback when no AI model is available. No AI in this file.

It reads a message with the helpers from dates.py, quantities.py and names.py, and produces
the same RawExtraction shape the model must return. Step 2d then checks both paths the same way.

Rules (agreed in v2 step 2c):
- Supplier / item: the one record the message names. Two or more → ambiguous flag.
- Quantity: see quantities.py ("remaining" wins; differing numbers → suggestions).
- Dates: if the delivery is known (supplier and item found, one open delivery), its due date is
  the original and every other date is a new-date candidate; two different candidates → conflict.
  If the delivery is not known: two dates → earliest is original, latest is new; one date →
  original if it equals an open delivery's due date for the item, otherwise new;
  three or more → ambiguous.
- Type: a new date or delay words → supplier_delay; shortfall words → supplier_shortfall;
  neither → left for the owner.
"""

from __future__ import annotations

import re
from datetime import date

from .dates import DateMention, find_date_mentions
from .names import scan_for_names
from .quantities import choose_affected_quantity, find_quantity_mentions
from .schemas import BusinessSnapshot, Delivery, DisruptionType, RawExtraction, RawFlag

OPEN_DELIVERY_STATUSES = {"scheduled", "delayed", "partially_delivered"}

SHORTFALL_WORDS = re.compile(
    r"\b(cannot supply|can't supply|can not supply|unable to supply|out of stock|cancel\w*|"
    r"won't come|will not come|not coming|no longer|cannot deliver at all)\b",
    re.IGNORECASE,
)
DELAY_WORDS = re.compile(r"\b(late|delay\w*|postpone\w*|reschedul\w*|will now)\b", re.IGNORECASE)


def rule_based_extract(message: str, snapshot: BusinessSnapshot, reported_on: date) -> RawExtraction:
    """Read a supplier message with keyword and pattern rules only."""
    flags: list[RawFlag] = []

    supplier_id, supplier_name = _one_name(
        message, {s.id: [s.name, *s.aliases] for s in snapshot.suppliers}, "supplier_id", "suppliers", flags)
    resource_id, resource_name = _one_name(
        message, {r.id: [r.name, *r.aliases] for r in snapshot.resources}, "resource_id", "items", flags)

    quantity = _quantity(message, snapshot, resource_id, flags)

    deliveries = _open_deliveries(snapshot, supplier_id, resource_id)
    known_delivery = deliveries[0] if supplier_id and resource_id and len(deliveries) == 1 else None
    anchor = known_delivery.expected_date if known_delivery else None
    mentions = find_date_mentions(message, reported_on, anchor)
    if known_delivery:
        original, new = _dates_with_known_delivery(mentions, known_delivery.expected_date, flags)
    else:
        due_dates = {d.expected_date for d in deliveries}
        original, new = _dates_without_delivery(mentions, due_dates, flags)

    return RawExtraction(
        disruption_type=_disruption_type(message, new, flags),
        supplier_name=supplier_name,
        resource_name=resource_name,
        quantity_affected=quantity,
        original_arrival_date=original,
        new_arrival_date=new,
        flags=flags,
    )


# --- Names and quantity ------------------------------------------------------------


def _one_name(message: str, names_by_id: dict[str, list[str]], field: str, what: str,
              flags: list[RawFlag]) -> tuple[str | None, str | None]:
    """Return (record ID, name as written) if the message names exactly one record; flag otherwise."""
    found = scan_for_names(message, names_by_id)
    if len(found) == 1:
        record_id, name = next(iter(found.items()))
        return record_id, name
    if found:
        flags.append(RawFlag(field=field, reason="ambiguous", candidates=sorted(found),
                             note=f"the message mentions several {what}"))
    else:
        flags.append(RawFlag(field=field, reason="missing", note=f"the message does not name any known {what}"))
    return None, None


def _quantity(message: str, snapshot: BusinessSnapshot, resource_id: str | None, flags: list[RawFlag]) -> int | None:
    """Find the affected quantity using the found item's words (or every item's, if none was found)."""
    resources = [r for r in snapshot.resources if resource_id is None or r.id == resource_id]
    item_words = [w for r in resources for w in (r.name, r.unit, *r.aliases)]
    choice = choose_affected_quantity(find_quantity_mentions(message, item_words))
    if choice.status == "ok":
        return choice.value
    flags.append(RawFlag(field="quantity_affected", reason=choice.status, note=choice.note,
                         candidates=[str(c) for c in choice.candidates]))
    return None


# --- Dates -------------------------------------------------------------------------


def _open_deliveries(snapshot: BusinessSnapshot, supplier_id: str | None, resource_id: str | None) -> list[Delivery]:
    """Open deliveries for the found item (and supplier, if found). Empty if the item is unknown."""
    if resource_id is None:
        return []
    return [
        d for d in snapshot.deliveries
        if d.status in OPEN_DELIVERY_STATUSES and d.resource_id == resource_id
        and (supplier_id is None or d.supplier_id == supplier_id)
    ]


def _exact_dates(mentions: list[DateMention]) -> list[tuple[date, str]]:
    """Distinct resolved dates in order of value, each with the first phrase that gave it."""
    first: dict[date, str] = {}
    for m in mentions:
        if m.status == "exact" and m.value and m.value not in first:
            first[m.value] = m.text
    return sorted(first.items())


def _flag_new_date_without_value(mentions: list[DateMention], flags: list[RawFlag]) -> None:
    """Explain why there is no new date: a vague phrase, a delay with no original, or nothing at all."""
    vague = next((m for m in mentions if m.status == "ambiguous"), None)
    delay = next((m for m in mentions if m.status == "needs_anchor"), None)
    if vague:
        flags.append(RawFlag(field="new_arrival_date", reason="ambiguous", note=f"'{vague.text}': {vague.note}"))
    elif delay:
        flags.append(RawFlag(field="new_arrival_date", reason="missing",
                             note=f"'{delay.text}': the original delivery date is unknown"))
    else:
        flags.append(RawFlag(field="new_arrival_date", reason="missing", note="the message gives no new date"))


def _dates_with_known_delivery(mentions: list[DateMention], due: date,
                               flags: list[RawFlag]) -> tuple[date | None, date | None]:
    """The delivery's due date is the original; any other date is a candidate for the new date."""
    found = _exact_dates(mentions)
    original = due if any(value == due for value, _ in found) else None
    new_candidates = [value for value, _ in found if value != due]
    if len(new_candidates) == 1:
        return original, new_candidates[0]
    if len(new_candidates) > 1:
        flags.append(RawFlag(field="new_arrival_date", reason="conflicting",
                             candidates=[d.isoformat() for d in new_candidates],
                             note="the message gives different new dates: "
                                  + ", ".join(f"{text} = {value.isoformat()}" for value, text in found if value != due)))
        return original, None
    _flag_new_date_without_value(mentions, flags)
    return original, None


def _dates_without_delivery(mentions: list[DateMention], due_dates: set[date],
                            flags: list[RawFlag]) -> tuple[date | None, date | None]:
    """Earliest/latest for two dates; a single date is the original only if it matches a due date."""
    found = [value for value, _ in _exact_dates(mentions)]
    if len(found) == 2:
        return found[0], found[1]
    if len(found) > 2:
        listed = [d.isoformat() for d in found]
        flags.append(RawFlag(field="new_arrival_date", reason="ambiguous", candidates=listed,
                             note="the message mentions more than two dates"))
        flags.append(RawFlag(field="original_arrival_date", reason="ambiguous", candidates=listed,
                             note="the message mentions more than two dates"))
        return None, None
    if len(found) == 1 and found[0] not in due_dates:
        return None, found[0]
    _flag_new_date_without_value(mentions, flags)
    return (found[0] if found else None), None


# --- Type --------------------------------------------------------------------------


def _disruption_type(message: str, new: date | None, flags: list[RawFlag]) -> DisruptionType | None:
    """A new date or delay words mean a delay; shortfall words mean a shortfall; else ask the owner."""
    if new is not None:
        return DisruptionType.SUPPLIER_DELAY
    if SHORTFALL_WORDS.search(message):
        return DisruptionType.SUPPLIER_SHORTFALL
    if DELAY_WORDS.search(message):
        return DisruptionType.SUPPLIER_DELAY
    flags.append(RawFlag(field="type", reason="missing", note="could not tell whether items are late or not coming"))
    return None
