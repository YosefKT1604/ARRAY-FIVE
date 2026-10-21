"""Combine the rules' and the model's readings of a message, check them, and build the result.

No AI in this file: it decides what to trust. Rules agreed in v2 step 2d:

    Model (M) vs rules (R), per field              Result
    M = R, nobody flagged doubt                    filled
    R found, model gave nothing                    filled (the rules read it from the message)
    M != R                                         blank; both suggested
    M only, rules flagged doubt                    blank; M + the rules' suggestions, the rules' reason
    M only, rules found nothing                    blank; M suggested ("only the AI found this")
    a flag of doubt while the values agree         blank; the value suggested
    neither has a value                            blank; any suggestions from the flags
    no model at all                                the rules' values, as they are

Then, for filled values:
- supplier: taken from the sender's contact when the message names none; a different named
  supplier than the sender is a conflict;
- delivery: the single open delivery for supplier + item; its due date fills a blank original date;
- checks: new date after the original, not before the report date, within 60 days of it;
  quantity no larger than the delivery. A failed check turns the value into a suggestion.

A blank field always has an entry in `unresolved_fields` saying why, and suggestions for the owner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .names import resolve_name
from .schemas import (
    MATERIAL_FIELDS,
    BusinessSnapshot,
    Delivery,
    DisruptionType,
    DraftIncident,
    ExtractionResult,
    InputSource,
    RawExtraction,
    RawFlag,
    UnresolvedField,
    UnresolvedReason,
)

OPEN_DELIVERY_STATUSES = {"scheduled", "delayed", "partially_delivered"}
MAX_DAYS_AHEAD = 60

# When several reasons apply to one field, the most serious one is reported.
REASON_PRIORITY = {
    UnresolvedReason.CONFLICTING: 5,
    UnresolvedReason.AMBIGUOUS: 4,
    UnresolvedReason.UNMATCHED: 3,
    UnresolvedReason.UNVERIFIED: 2,
    UnresolvedReason.MISSING: 1,
}

FIELD_LABELS = {
    "type": "the type of disruption",
    "supplier_id": "the supplier",
    "resource_id": "the affected item",
    "delivery_id": "the delivery order",
    "quantity_affected": "how many units are affected",
    "original_arrival_date": "the original delivery date",
    "new_arrival_date": "the new arrival date",
}


@dataclass
class Doubt:
    """A reason not to trust a field, with suggestions for the owner."""

    reason: UnresolvedReason
    note: str = ""
    candidates: list[str] = field(default_factory=list)
    raw_value: str | None = None


@dataclass
class Reading:
    """What one extractor (model or rules) said about one field: a value and/or a doubt."""

    value: Any = None
    doubt: Doubt | None = None


@dataclass
class Merged:
    """The outcome for one field: a trusted value with its source, or a doubt."""

    value: Any = None
    source: str = ""
    doubt: Doubt | None = None


# --- Public entry point -----------------------------------------------------------


def combine(
    rules: RawExtraction,
    model: RawExtraction | None,
    snapshot: BusinessSnapshot,
    reported_at: datetime,
    *,
    sender: str | None = None,
    generated_by: str = "template",
    warnings: list[str] | None = None,
) -> ExtractionResult:
    """Merge the two readings field by field, apply the checks, and build the ExtractionResult.

    `model` is None when no model was used (unavailable, timed out or invalid reply).
    """
    reported_on = reported_at.date()
    suppliers = {s.id: [s.name, *s.aliases] for s in snapshot.suppliers}
    resources = {r.id: [r.name, *r.aliases] for r in snapshot.resources}

    merged: dict[str, Merged] = {
        "type": merge(_plain(rules, "type", rules.disruption_type), _plain(model, "type", model and model.disruption_type)),
        "supplier_id": merge(_named(rules, "supplier_id", rules.supplier_name, suppliers),
                             _named(model, "supplier_id", model and model.supplier_name, suppliers)),
        "resource_id": merge(_named(rules, "resource_id", rules.resource_name, resources),
                             _named(model, "resource_id", model and model.resource_name, resources)),
        "quantity_affected": merge(_plain(rules, "quantity_affected", rules.quantity_affected),
                                   _plain(model, "quantity_affected", model and model.quantity_affected)),
        "original_arrival_date": merge(_plain(rules, "original_arrival_date", rules.original_arrival_date),
                                       _plain(model, "original_arrival_date", model and model.original_arrival_date)),
        "new_arrival_date": merge(_plain(rules, "new_arrival_date", rules.new_arrival_date),
                                  _plain(model, "new_arrival_date", model and model.new_arrival_date)),
    }
    if model is None:
        for item in merged.values():
            if item.value is not None:
                item.source = "rules (no model used)"

    apply_sender(merged["supplier_id"], _supplier_from_sender(sender, snapshot), sender, snapshot)
    delivery = find_delivery(merged, snapshot)
    apply_checks(merged, delivery, reported_on)

    for name, item in merged.items():
        if item.value is None and item.doubt is None:
            item.doubt = Doubt(UnresolvedReason.MISSING, note=f"{FIELD_LABELS[name]} could not be determined")

    unresolved = [
        UnresolvedField(field=name, reason=item.doubt.reason, raw_value=item.doubt.raw_value,
                        candidates=item.doubt.candidates, note=item.doubt.note)
        for name, item in merged.items() if item.value is None
    ]
    values = {name: item.value for name, item in merged.items()}
    draft = DraftIncident(
        type=values["type"],
        source=InputSource.MESSAGE,
        supplier_id=values["supplier_id"],
        resource_id=values["resource_id"],
        delivery_id=values["delivery_id"],
        quantity_affected=values["quantity_affected"],
        original_arrival_date=values["original_arrival_date"],
        new_arrival_date=values["new_arrival_date"],
        description=describe(values, snapshot),
        reported_at=reported_at,
        unresolved_fields=unresolved,
    )
    return ExtractionResult(
        draft_incident=draft,
        field_evidence={name: item.source for name, item in merged.items() if item.value is not None},
        unresolved_fields=unresolved,
        needs_clarification=any(u.field in MATERIAL_FIELDS for u in unresolved),
        clarification_questions=[question(u) for u in unresolved if u.field in MATERIAL_FIELDS],
        generated_by=generated_by,
        fallback_used=model is None,
        warnings=list(warnings or []),
    )


# --- Readings ----------------------------------------------------------------------


def _as_text(value: Any) -> str:
    """Turn a value into the text used in suggestions: IDs, numbers, ISO dates, enum values."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, DisruptionType):
        return value.value
    return str(value)


def _flag_for(raw: RawExtraction | None, field_name: str) -> RawFlag | None:
    """The extractor's own flag for this field, if it raised one."""
    if raw is None:
        return None
    return next((f for f in raw.flags if f.field == field_name), None)


def _plain(raw: RawExtraction | None, field_name: str, value: Any) -> Reading | None:
    """A reading for a field whose value needs no lookup (quantity, dates, type)."""
    if raw is None:
        return None
    flag = _flag_for(raw, field_name)
    doubt = Doubt(UnresolvedReason(flag.reason), flag.note, list(flag.candidates)) if flag else None
    return Reading(value, doubt)


def _named(raw: RawExtraction | None, field_name: str, name: str | None, names_by_id: dict) -> Reading | None:
    """A reading for supplier/item: the name is mapped to a record ID, or becomes a doubt."""
    reading = _plain(raw, field_name, None)
    if reading is None or not name:
        return reading
    match = resolve_name(name, names_by_id)
    if match.status == "matched":
        reading.value = match.entity_id
    elif reading.doubt is None or REASON_PRIORITY[reading.doubt.reason] < REASON_PRIORITY[UnresolvedReason.UNMATCHED]:
        reason = UnresolvedReason.AMBIGUOUS if match.status == "ambiguous" else UnresolvedReason.UNMATCHED
        note = "matches more than one record" if match.status == "ambiguous" else "no known record has this name"
        reading.doubt = Doubt(reason, f"'{name}': {note}", match.candidates, raw_value=name)
    return reading


def _union(*lists: list[str]) -> list[str]:
    """Join suggestion lists, keeping order and dropping duplicates."""
    return list(dict.fromkeys(item for items in lists for item in items))


def _seriousness(doubt: Doubt) -> int:
    """Sort key: how serious a doubt's reason is (see REASON_PRIORITY)."""
    return REASON_PRIORITY[doubt.reason]


def _worst(*doubts: Doubt | None) -> Doubt | None:
    """The most serious of several doubts (or None)."""
    present = [d for d in doubts if d is not None]
    return max(present, key=_seriousness) if present else None


# --- The combination table ------------------------------------------------------------


def merge(rules: Reading, model: Reading | None) -> Merged:
    """Apply the combination table (module docstring) to one field."""
    r, dr = rules.value, rules.doubt
    if model is None:  # no model: rules only
        if r is not None and dr is not None:  # a value with a doubt: suggest it, as in the model branch
            return Merged(doubt=Doubt(dr.reason, dr.note, _union([_as_text(r)], dr.candidates), dr.raw_value))
        return Merged(r, "rules") if r is not None else Merged(doubt=dr)

    m, dm = model.value, model.doubt
    flag_candidates = _union(dr.candidates if dr else [], dm.candidates if dm else [])

    if r is not None and m is not None and m != r:
        return Merged(doubt=Doubt(UnresolvedReason.CONFLICTING, "the AI model and the rules disagree",
                                  _union([_as_text(r), _as_text(m)], flag_candidates)))
    if r is not None:  # m is None or equal to r
        if dr is None and dm is None:
            return Merged(r, "rules and AI model agree" if m is not None else "rules (AI model gave no value)")
        worst = _worst(dr, dm)
        return Merged(doubt=Doubt(worst.reason, worst.note, _union([_as_text(r)], flag_candidates), worst.raw_value))
    if m is not None:  # only the model has a value
        if dr is not None and dr.reason in (UnresolvedReason.AMBIGUOUS, UnresolvedReason.CONFLICTING):
            return Merged(doubt=Doubt(dr.reason, dr.note, _union(dr.candidates, [_as_text(m)]), dr.raw_value))
        return Merged(doubt=Doubt(UnresolvedReason.UNVERIFIED, "only the AI model found this; please confirm",
                                  _union([_as_text(m)], flag_candidates)))
    worst = _worst(dr, dm)
    if worst is None:
        return Merged()
    return Merged(doubt=Doubt(worst.reason, worst.note, flag_candidates, worst.raw_value))


# --- Sender, delivery and checks -----------------------------------------------------------


def _supplier_from_sender(sender: str | None, snapshot: BusinessSnapshot) -> str | None:
    """The supplier whose contact_reference is exactly the sender (ignoring case), or None."""
    if not sender:
        return None
    hits = [s.id for s in snapshot.suppliers
            if s.contact_reference and s.contact_reference.strip().lower() == sender.strip().lower()]
    return hits[0] if len(hits) == 1 else None


def _supplier_name(supplier_id: str, snapshot: BusinessSnapshot) -> str:
    """The supplier's name for notes shown to the owner (the ID if it is not found)."""
    return next((s.name for s in snapshot.suppliers if s.id == supplier_id), supplier_id)


def apply_sender(supplier: Merged, sender_id: str | None, sender: str | None, snapshot: BusinessSnapshot) -> None:
    """Use the sender's contact to fill, confirm or contradict the supplier."""
    if sender_id is None:
        return
    if supplier.value == sender_id:
        supplier.source += f"; confirmed by sender contact {sender}"
    elif supplier.value is not None:
        named, sent_by = _supplier_name(supplier.value, snapshot), _supplier_name(sender_id, snapshot)
        supplier.doubt = Doubt(UnresolvedReason.CONFLICTING,
                               f"the message names {named} but was sent by {sent_by}'s contact",
                               [supplier.value, sender_id])
        supplier.value = None
    elif supplier.doubt is None or supplier.doubt.reason == UnresolvedReason.MISSING:
        supplier.value, supplier.source, supplier.doubt = sender_id, f"sender contact {sender}", None
    elif supplier.doubt.reason in (UnresolvedReason.AMBIGUOUS, UnresolvedReason.UNVERIFIED) \
            and supplier.doubt.candidates == [sender_id]:
        supplier.value, supplier.source, supplier.doubt = sender_id, f"sender contact {sender} (matches the AI's reading)", None
    elif sender_id not in supplier.doubt.candidates:
        supplier.doubt.candidates.append(sender_id)


def find_delivery(merged: dict[str, Merged], snapshot: BusinessSnapshot) -> Delivery | None:
    """Find the open delivery for the supplier and item; record it as the `delivery_id` field."""
    supplier_id, resource_id = merged["supplier_id"].value, merged["resource_id"].value
    original = merged["original_arrival_date"].value
    if supplier_id is None or resource_id is None:
        possible = [d.id for d in snapshot.deliveries if d.status in OPEN_DELIVERY_STATUSES
                    and (resource_id is None or d.resource_id == resource_id)
                    and (supplier_id is None or d.supplier_id == supplier_id)]
        merged["delivery_id"] = Merged(doubt=Doubt(UnresolvedReason.MISSING, "confirm the supplier and item first",
                                                   possible if resource_id or supplier_id else []))
        return None
    found = [d for d in snapshot.deliveries if d.status in OPEN_DELIVERY_STATUSES
             and d.supplier_id == supplier_id and d.resource_id == resource_id]
    if original is not None and any(d.expected_date == original for d in found):
        found = [d for d in found if d.expected_date == original]
    if len(found) == 1:
        merged["delivery_id"] = Merged(found[0].id, "open delivery for this supplier and item")
        return found[0]
    reason = UnresolvedReason.AMBIGUOUS if found else UnresolvedReason.MISSING
    note = "several open deliveries match" if found else "no open delivery from this supplier for this item"
    merged["delivery_id"] = Merged(doubt=Doubt(reason, note, [d.id for d in found]))
    return None


def _reject(item: Merged, reason: UnresolvedReason, note: str, extra: list[str] | None = None) -> None:
    """Turn a filled value into a suggestion because a check failed."""
    item.doubt = Doubt(reason, note, _union([_as_text(item.value)], extra or []))
    item.value, item.source = None, ""


def apply_checks(merged: dict[str, Merged], delivery: Delivery | None, reported_on: date) -> None:
    """Fill the original date from the delivery, then run the plausibility checks."""
    original, new, quantity = merged["original_arrival_date"], merged["new_arrival_date"], merged["quantity_affected"]

    if delivery is not None:
        if original.value is None and (original.doubt is None or original.doubt.reason == UnresolvedReason.MISSING):
            original.value, original.source, original.doubt = delivery.expected_date, f"delivery {delivery.id} due date", None
        elif original.value is not None and original.value != delivery.expected_date:
            _reject(original, UnresolvedReason.CONFLICTING,
                    f"delivery {delivery.id} is due {delivery.expected_date.isoformat()}", [delivery.expected_date.isoformat()])
        if quantity.value is not None and quantity.value > delivery.quantity:
            _reject(quantity, UnresolvedReason.CONFLICTING, f"more than the {delivery.quantity} units on delivery {delivery.id}")

    if new.value is not None:
        if original.value is not None and new.value <= original.value:
            _reject(new, UnresolvedReason.CONFLICTING, f"not after the original date {original.value.isoformat()}")
        elif new.value < reported_on:
            _reject(new, UnresolvedReason.CONFLICTING, f"before the report date {reported_on.isoformat()}")
        elif new.value > reported_on + timedelta(days=MAX_DAYS_AHEAD):
            _reject(new, UnresolvedReason.UNVERIFIED, f"more than {MAX_DAYS_AHEAD} days after the report; please confirm")


# --- Description and questions ------------------------------------------------------------


def describe(values: dict[str, Any], snapshot: BusinessSnapshot) -> str:
    """One-line description built from the filled values only."""
    supplier = next((s for s in snapshot.suppliers if s.id == values["supplier_id"]), None)
    resource = next((r for r in snapshot.resources if r.id == values["resource_id"]), None)
    item = resource.name.lower() if resource else "items"
    what = f"{values['quantity_affected']} {item}" if values["quantity_affected"] else f"an unconfirmed number of {item}"
    shortfall = values["type"] == DisruptionType.SUPPLIER_SHORTFALL
    verb = "cannot be supplied" if shortfall else "will be late"
    text = f"{supplier.name if supplier else 'A supplier'} reports that {what} {verb}"
    if values["original_arrival_date"]:
        text += f" (originally due {values['original_arrival_date'].isoformat()})"
    new = values["new_arrival_date"]
    if new:
        return text + f"; now expected {new.isoformat()}."
    return text + ("." if shortfall else "; new arrival date not confirmed.")


def question(item: UnresolvedField) -> str:
    """The question shown to the owner for one blank material field."""
    label = FIELD_LABELS[item.field]
    text = f"Please confirm {label}: {item.note}." if item.note else f"Please confirm {label}."
    return text + (f" Suggestions: {', '.join(item.candidates)}." if item.candidates else "")
