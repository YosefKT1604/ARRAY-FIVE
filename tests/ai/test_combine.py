"""Tests for combine.py: the combination table, the sender rule, the delivery lookup and the checks."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from scdc.ai.combine import combine
from scdc.ai.rules import rule_based_extract
from scdc.ai.schemas import RawExtraction, RawFlag

from .conftest import DEMO_MESSAGE, REPORTED_ON

REPORTED_AT = datetime(2026, 10, 20, 10, 15, tzinfo=timezone(timedelta(hours=8)))
MAJU = "whatsapp:maju-rental (synthetic)"
BASE = {
    "disruption_type": "supplier_delay", "supplier_name": "Maju", "resource_name": "chairs",
    "quantity_affected": 20, "original_arrival_date": date(2026, 10, 21), "new_arrival_date": date(2026, 10, 23),
}


def raw(**changes) -> RawExtraction:
    """A complete, correct reading of the demo incident, with some fields changed."""
    return RawExtraction(**{**BASE, **changes})


def unresolved(result) -> dict:
    """Map each blank field to its UnresolvedField, for short assertions."""
    return {u.field: u for u in result.unresolved_fields}


# --- No model (fallback) ---------------------------------------------------------------


def test_rules_only_demo_with_sender_is_fully_filled(snapshot):
    """Demo message + Maju's contact, no model: every field is filled and linked to DL-01."""
    rules = rule_based_extract(DEMO_MESSAGE, snapshot, REPORTED_ON)
    result = combine(rules, None, snapshot, REPORTED_AT, sender=MAJU)
    d = result.draft_incident
    assert (d.supplier_id, d.resource_id, d.delivery_id, d.quantity_affected) == ("S-01", "R-01", "DL-01", 20)
    assert (d.original_arrival_date, d.new_arrival_date) == (date(2026, 10, 21), date(2026, 10, 23))
    assert result.unresolved_fields == [] and not result.needs_clarification
    assert result.fallback_used and result.field_evidence["supplier_id"].startswith("sender contact")


def test_rules_only_demo_without_sender_asks_for_the_supplier(snapshot):
    """Without the sender, the supplier stays blank; DL-01 is suggested for the delivery."""
    rules = rule_based_extract(DEMO_MESSAGE, snapshot, REPORTED_ON)
    result = combine(rules, None, snapshot, REPORTED_AT)
    blank = unresolved(result)
    assert blank["supplier_id"].reason.value == "missing"
    assert blank["delivery_id"].candidates == ["DL-01"]
    assert result.needs_clarification and any("supplier" in q for q in result.clarification_questions)


# --- The combination table ----------------------------------------------------------------


def test_model_agrees_fills_every_field(snapshot):
    """M = R everywhere: filled, with 'agree' as the evidence."""
    result = combine(raw(), raw(), snapshot, REPORTED_AT, generated_by="model:mock")
    assert result.unresolved_fields == [] and not result.fallback_used
    assert result.field_evidence["quantity_affected"] == "found in the message; the AI agrees"
    assert result.generated_by == "model:mock"


def test_model_gives_nothing_rules_value_is_used(snapshot):
    """R found, model silent: the rules' value fills the field."""
    result = combine(raw(), raw(quantity_affected=None), snapshot, REPORTED_AT)
    assert result.draft_incident.quantity_affected == 20
    assert result.field_evidence["quantity_affected"] == "found in the message (the AI gave no value)"


def test_model_and_rules_disagree(snapshot):
    """M != R: blank, both values suggested."""
    result = combine(raw(), raw(quantity_affected=40), snapshot, REPORTED_AT)
    item = unresolved(result)["quantity_affected"]
    assert result.draft_incident.quantity_affected is None
    assert item.reason.value == "conflicting" and item.candidates == ["20", "40"]


def test_model_only_value_is_a_suggestion(snapshot):
    """Rules found no quantity (no doubt either), model says 20: blank, 20 suggested."""
    result = combine(raw(quantity_affected=None), raw(), snapshot, REPORTED_AT)
    item = unresolved(result)["quantity_affected"]
    assert item.reason.value == "unverified" and item.candidates == ["20"]
    assert "only the AI" in item.note


def test_model_value_where_rules_had_doubt(snapshot):
    """Rules: 'next week' is ambiguous. Model: 27 Oct. Blank, with the rules' reason and 27 Oct suggested."""
    rules = raw(new_arrival_date=None,
                flags=[RawFlag(field="new_arrival_date", reason="ambiguous", note="'next week': vague timing")])
    result = combine(rules, raw(new_arrival_date=date(2026, 10, 27)), snapshot, REPORTED_AT)
    item = unresolved(result)["new_arrival_date"]
    assert item.reason.value == "ambiguous" and "next week" in item.note
    assert "2026-10-27" in item.candidates


def test_model_doubt_blocks_an_agreed_value(snapshot):
    """Both say 20, but the model flags the quantity as ambiguous: blank, 20 suggested."""
    model = raw(flags=[RawFlag(field="quantity_affected", reason="ambiguous", note="20 or 30?")])
    item = unresolved(combine(raw(), model, snapshot, REPORTED_AT))["quantity_affected"]
    assert item.reason.value == "ambiguous" and item.candidates == ["20"]


def test_model_missing_flag_is_silence(snapshot):
    """Model: 'can't work out the new date' (missing). Rules found 23 Oct: filled, as if the model were silent."""
    model = raw(new_arrival_date=None, flags=[RawFlag(field="new_arrival_date", reason="missing")])
    result = combine(raw(), model, snapshot, REPORTED_AT)
    assert result.draft_incident.new_arrival_date == date(2026, 10, 23)
    assert result.field_evidence["new_arrival_date"] == "found in the message (the AI gave no value)"


def test_unknown_supplier_name_from_model_is_unmatched(snapshot):
    """Model names 'Bintang Rentals', which is not a known supplier."""
    rules = raw(supplier_name=None, flags=[RawFlag(field="supplier_id", reason="missing")])
    item = unresolved(combine(rules, raw(supplier_name="Bintang Rentals"), snapshot, REPORTED_AT))["supplier_id"]
    assert item.reason.value == "unmatched" and item.raw_value == "Bintang Rentals"


# --- Sender -------------------------------------------------------------------------------


def test_sender_confirms_named_supplier(snapshot):
    """The message names Maju and comes from Maju's contact: filled, evidence mentions both."""
    result = combine(raw(), None, snapshot, REPORTED_AT, sender=MAJU)
    assert result.draft_incident.supplier_id == "S-01"
    assert "confirmed by sender" in result.field_evidence["supplier_id"]


def test_named_supplier_differs_from_sender(snapshot):
    """The message says Cahaya but comes from Maju's contact: blank, both suggested; the note uses names."""
    item = unresolved(combine(raw(supplier_name="Cahaya"), None, snapshot, REPORTED_AT, sender=MAJU))["supplier_id"]
    assert item.reason.value == "conflicting" and set(item.candidates) == {"S-01", "S-02"}
    assert "Cahaya" in item.note and "Maju" in item.note and "S-0" not in item.note


# --- Delivery and checks ------------------------------------------------------------------


def test_original_date_comes_from_the_delivery(snapshot):
    """No original date in the message: filled from DL-01's due date."""
    result = combine(raw(original_arrival_date=None), None, snapshot, REPORTED_AT)
    assert result.draft_incident.original_arrival_date == date(2026, 10, 21)
    assert result.field_evidence["original_arrival_date"] == "delivery DL-01 due date"


def test_model_only_original_date_confirmed_by_delivery(snapshot):
    """Only the model gave 21 Oct, which is DL-01's due date: filled from the delivery."""
    result = combine(raw(original_arrival_date=None), raw(), snapshot, REPORTED_AT)
    assert result.draft_incident.original_arrival_date == date(2026, 10, 21)
    assert "matches the AI's reading" in result.field_evidence["original_arrival_date"]


def test_model_only_original_date_not_matching_delivery_is_asked(snapshot):
    """Only the model gave 22 Oct, but DL-01 is due 21 Oct: still blank, 22 Oct suggested."""
    model = raw(original_arrival_date=date(2026, 10, 22))
    item = unresolved(combine(raw(original_arrival_date=None), model, snapshot, REPORTED_AT))["original_arrival_date"]
    assert item.reason.value == "unverified" and item.candidates == ["2026-10-22"]


def test_original_date_that_contradicts_the_delivery(snapshot):
    """The message says 22 Oct but DL-01 is due 21 Oct: blank, both suggested."""
    item = unresolved(combine(raw(original_arrival_date=date(2026, 10, 22)), None, snapshot, REPORTED_AT))
    assert item["original_arrival_date"].reason.value == "conflicting"
    assert item["original_arrival_date"].candidates == ["2026-10-22", "2026-10-21"]


def test_new_date_not_after_original(snapshot):
    """A 'delay' to the original date (or earlier) is not plausible."""
    item = unresolved(combine(raw(new_arrival_date=date(2026, 10, 21)), None, snapshot, REPORTED_AT))["new_arrival_date"]
    assert item.reason.value == "conflicting" and "not after the original" in item.note


def test_new_date_before_the_report(snapshot):
    """With no original date known, a new date before the report day is still rejected."""
    rules = raw(supplier_name=None, original_arrival_date=None, new_arrival_date=date(2026, 10, 19))
    item = unresolved(combine(rules, None, snapshot, REPORTED_AT))["new_arrival_date"]
    assert item.reason.value == "conflicting" and "before the report date" in item.note


def test_new_date_too_far_ahead(snapshot):
    """More than 60 days after the report: blank, the date suggested for confirmation."""
    item = unresolved(combine(raw(new_arrival_date=date(2027, 1, 5)), None, snapshot, REPORTED_AT))["new_arrival_date"]
    assert item.reason.value == "unverified" and item.candidates == ["2027-01-05"]


def test_quantity_larger_than_delivery(snapshot):
    """50 chairs late on a 40-chair delivery is not plausible."""
    item = unresolved(combine(raw(quantity_affected=50), None, snapshot, REPORTED_AT))["quantity_affected"]
    assert item.reason.value == "conflicting" and "40 units" in item.note


def test_rules_value_with_doubt_is_suggested_without_model(snapshot):
    """No model; rules read 20 but flagged it: blank, and 20 is still among the suggestions."""
    rules = raw(flags=[RawFlag(field="quantity_affected", reason="ambiguous", note="20 or 30?", candidates=["30"])])
    item = unresolved(combine(rules, None, snapshot, REPORTED_AT))["quantity_affected"]
    assert item.reason.value == "ambiguous" and item.candidates == ["20", "30"]


# --- Description --------------------------------------------------------------------------


def test_delay_description(snapshot):
    """The demo delay reads as a late delivery with its new date."""
    text = combine(raw(), None, snapshot, REPORTED_AT, sender=MAJU).draft_incident.description
    assert "will be late" in text and "now expected 2026-10-23" in text


def test_shortfall_description(snapshot):
    """A shortfall says the items cannot be supplied, and does not ask for a new date."""
    rules = raw(disruption_type="supplier_shortfall", new_arrival_date=None)
    text = combine(rules, None, snapshot, REPORTED_AT, sender=MAJU).draft_incident.description
    assert "cannot be supplied" in text and "will be late" not in text and "new arrival date" not in text


def test_every_blank_field_is_explained(snapshot):
    """Invariant: any empty field in the draft has an unresolved entry."""
    rules = rule_based_extract("Maju here, question about the chairs.", snapshot, REPORTED_ON)
    result = combine(rules, None, snapshot, REPORTED_AT)
    draft = result.draft_incident.model_dump()
    blank_fields = {u.field for u in result.unresolved_fields}
    for name in ("type", "supplier_id", "resource_id", "delivery_id", "quantity_affected",
                 "original_arrival_date", "new_arrival_date"):
        assert (draft[name] is None) == (name in blank_fields), name
