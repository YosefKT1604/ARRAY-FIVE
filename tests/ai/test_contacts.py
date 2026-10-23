"""Tests for identifying the sender from WhatsApp contact details (phone number, the owner's saved contact name)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scdc.ai.contacts import identify_sender, normalise_phone
from scdc.ai.extraction import extract_from_message
from scdc.ai.schemas import IncomingMessage

from .conftest import DEMO_MESSAGE

RECEIVED_AT = datetime(2026, 10, 20, 10, 15, tzinfo=timezone(timedelta(hours=8)))
PHONES = {"S-01": "+60 12-345 6789", "S-02": "013-222 3344", "S-03": "+603-8888 1234"}


@pytest.fixture
def with_phones(snapshot):
    """The demo data with phone numbers on the suppliers (a copy; fixtures/demo is not changed)."""
    copy = snapshot.model_copy(deep=True)
    for supplier in copy.suppliers:
        supplier.phone = PHONES[supplier.id]
    return copy


def blank(result):
    """Map each blank field to its UnresolvedField."""
    return {u.field: u for u in result.unresolved_fields}


# --- Phone numbers --------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("+60 12-345 6789", "60123456789"), ("012-345 6789", "60123456789"), ("60123456789", "60123456789"),
    ("0060 12 345 6789", "60123456789"), ("+65 9123 4567", "6591234567"), ("12345", None), ("", None), (None, None),
])
def test_normalise_phone(raw, expected):
    """Different ways of writing a number give the same digits; too-short text is not a number."""
    assert normalise_phone(raw) == expected


# --- Identifying the sender -------------------------------------------------------------------------


def test_phone_identifies_the_supplier(with_phones):
    """Maju's number written differently still finds S-01."""
    match = identify_sender(with_phones, phone="0123456789")
    assert match.supplier_id == "S-01" and match.label == "sender phone +60123456789"


def test_saved_contact_name_identifies_the_supplier(with_phones):
    """The owner saved Cahaya's number as 'Pn Siti Cahaya': S-02."""
    match = identify_sender(with_phones, contact_name="Pn Siti Cahaya")
    assert match.supplier_id == "S-02" and "saved contact name 'Pn Siti Cahaya'" in match.label


def test_phone_and_name_agree(with_phones):
    """Both clues point to Maju: one supplier, both clues in the evidence."""
    match = identify_sender(with_phones, phone="+60 12-345 6789", contact_name="Ali Maju Rental")
    assert match.supplier_id == "S-01" and "phone" in match.label and "Ali Maju Rental" in match.label


def test_phone_and_name_disagree(with_phones):
    """Maju's number but saved as 'Cahaya': a conflict, both suggested."""
    match = identify_sender(with_phones, phone="+60 12-345 6789", contact_name="Cahaya")
    assert match.supplier_id is None and match.conflict == ["S-01", "S-02"]


def test_unknown_number_and_typo_name_only_suggest(with_phones):
    """An unknown number and a misspelt name ('Maaju Rental'): no supplier, Maju only suggested."""
    match = identify_sender(with_phones, phone="+60 19-999 0000", contact_name="Maaju Rental")
    assert match.supplier_id is None and match.conflict == [] and match.suggestions == ["S-01"]


def test_no_contact_details(with_phones):
    """Nothing given: nothing to say."""
    assert identify_sender(with_phones) is None


# --- Extraction from a WhatsApp message ----------------------------------------------------------


def test_demo_message_identified_by_phone_and_name(with_phones):
    """The demo message never names Maju; the number and saved name do. Everything is filled."""
    incoming = IncomingMessage(text=DEMO_MESSAGE, received_at=RECEIVED_AT,
                               from_number="012-345 6789", contact_name="Ali Maju Rental")
    result = extract_from_message(incoming, with_phones)
    d = result.draft_incident
    assert (d.supplier_id, d.delivery_id, d.quantity_affected, d.new_arrival_date.isoformat()) == (
        "S-01", "DL-01", 20, "2026-10-23")
    assert result.field_evidence["supplier_id"].startswith("sender phone +60123456789 and saved contact name")
    assert d.reported_at == RECEIVED_AT and not result.needs_clarification


def test_message_naming_another_supplier_is_a_conflict(with_phones):
    """'Cahaya here' from Maju's number: the owner decides."""
    incoming = IncomingMessage(text="Cahaya here, 20 chairs will be late until Friday.", received_at=RECEIVED_AT,
                               from_number="+60 12-345 6789")
    item = blank(extract_from_message(incoming, with_phones))["supplier_id"]
    assert item.reason.value == "conflicting" and set(item.candidates) == {"S-01", "S-02"}


def test_conflicting_contact_details(with_phones):
    """Number and saved name disagree: supplier blank, both suggested, explained by names."""
    incoming = IncomingMessage(text=DEMO_MESSAGE, received_at=RECEIVED_AT,
                               from_number="+60 12-345 6789", contact_name="Cahaya")
    item = blank(extract_from_message(incoming, with_phones))["supplier_id"]
    assert item.reason.value == "conflicting" and item.candidates == ["S-01", "S-02"]
    assert "Maju Rental Supplies" in item.note and "Cahaya Event Rentals" in item.note


def test_typo_name_becomes_a_suggestion(with_phones):
    """A misspelt saved name only suggests Maju; the supplier stays blank."""
    incoming = IncomingMessage(text=DEMO_MESSAGE, received_at=RECEIVED_AT, contact_name="Maaju Rental")
    item = blank(extract_from_message(incoming, with_phones))["supplier_id"]
    assert item.candidates == ["S-01"]


def test_contact_details_never_reach_the_model(with_phones):
    """Privacy: the model request contains the message only, not the number or the saved name."""
    from scdc.ai.adapter import MockAdapter
    adapter = MockAdapter({"extract_incident": RuntimeError("no model in this test")})
    extract_from_message(IncomingMessage(text=DEMO_MESSAGE, received_at=RECEIVED_AT, from_number="012-345 6789",
                                         contact_name="Ali Maju Rental"), with_phones, adapter=adapter)
    assert "345" not in adapter.calls[0].user and "Ali" not in adapter.calls[0].user


def test_demo_supplier_message_shape_is_accepted(snapshot):
    """The team's demo `supplier_message` (with from_contact) fits IncomingMessage and still finds Maju."""
    import json
    from .conftest import DEMO_FIXTURES
    raw = json.loads((DEMO_FIXTURES / "incident.json").read_text(encoding="utf-8"))["supplier_message"]
    result = extract_from_message(IncomingMessage.model_validate(raw), snapshot)
    assert result.draft_incident.supplier_id == "S-01"
