"""Tests for the rule-based extractor (the no-model fallback), using the demo business data."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from scdc.ai.rules import rule_based_extract
from scdc.ai.schemas import RawExtraction

from .conftest import DEMO_MESSAGE, REPORTED_ON


def flags_by_field(raw: RawExtraction) -> dict[str, str]:
    """Map each flagged field to its reason, for short assertions."""
    return {f.field: f.reason for f in raw.flags}


def test_demo_message(snapshot):
    """The demo message: chairs, 20, tomorrow → Friday. The supplier is not named in it."""
    raw = rule_based_extract(DEMO_MESSAGE, snapshot, REPORTED_ON)
    assert raw.resource_name == "chairs" and raw.quantity_affected == 20
    assert raw.original_arrival_date == date(2026, 10, 21)
    assert raw.new_arrival_date == date(2026, 10, 23)
    assert raw.disruption_type.value == "supplier_delay"
    assert raw.supplier_name is None and flags_by_field(raw) == {"supplier_id": "missing"}


def test_named_supplier_and_explicit_dates(snapshot):
    """Supplier, item, quantity and both dates written out."""
    raw = rule_based_extract("Hi, Maju Rental here. The 40 folding chairs due on 21 Oct will now arrive on 24 Oct.",
                             snapshot, REPORTED_ON)
    assert (raw.supplier_name, raw.resource_name, raw.quantity_affected) == ("Maju Rental", "Folding Chairs", 40)
    assert (raw.original_arrival_date, raw.new_arrival_date) == (date(2026, 10, 21), date(2026, 10, 24))
    assert raw.flags == []


def test_known_delivery_resolves_a_delay(snapshot):
    """With Maju's chair delivery known (due 21 Oct), 'two days late' means 23 Oct."""
    raw = rule_based_extract("Maju here, the 20 chairs will be two days late.", snapshot, REPORTED_ON)
    assert raw.new_arrival_date == date(2026, 10, 23)


def test_contradictory_new_dates_are_flagged(snapshot):
    """'three days late' (24 Oct) vs 'Friday' (23 Oct): neither is chosen; both suggested."""
    raw = rule_based_extract("Maju here. Our chair delivery will be three days late. "
                             "The remaining 20 chairs will come on Friday.", snapshot, REPORTED_ON)
    flag = next(f for f in raw.flags if f.field == "new_arrival_date")
    assert raw.new_arrival_date is None and flag.reason == "conflicting"
    assert flag.candidates == ["2026-10-23", "2026-10-24"]


def test_vague_date_is_flagged_not_guessed(snapshot):
    """'next week' gives no new date and an ambiguous flag."""
    raw = rule_based_extract("Maju here. The remaining 20 chairs will come next week.", snapshot, REPORTED_ON)
    assert raw.new_arrival_date is None and flags_by_field(raw)["new_arrival_date"] == "ambiguous"


def test_delay_without_known_delivery_is_missing(snapshot):
    """An unknown sender's 'two days late' cannot be resolved: there is no original date."""
    raw = rule_based_extract("Hi, this is Bintang Rentals. Your 20 chairs will be two days late.", snapshot, REPORTED_ON)
    flags = flags_by_field(raw)
    assert raw.new_arrival_date is None and flags["new_arrival_date"] == "missing"
    assert flags["supplier_id"] == "missing"


def test_single_date_matching_a_due_date_is_the_original(snapshot):
    """Without a known supplier, a date equal to the chairs' due date (21 Oct) is the original."""
    raw = rule_based_extract("The chairs for 21 Oct will be late.", snapshot, REPORTED_ON)
    assert raw.original_arrival_date == date(2026, 10, 21) and raw.new_arrival_date is None


def test_three_dates_are_ambiguous(snapshot):
    """Three different dates without a known delivery: the owner decides."""
    raw = rule_based_extract("The chairs: 21 Oct, maybe 23 Oct or 25 Oct.", snapshot, REPORTED_ON)
    assert raw.original_arrival_date is None and raw.new_arrival_date is None
    assert flags_by_field(raw)["new_arrival_date"] == "ambiguous"


def test_conflicting_quantities_become_suggestions(snapshot):
    """'20 chairs ... correction, 30 chairs': no quantity, both suggested."""
    raw = rule_based_extract("Maju here. 20 chairs will be late, coming Friday. Sorry correction, 30 chairs will be late.",
                             snapshot, REPORTED_ON)
    flag = next(f for f in raw.flags if f.field == "quantity_affected")
    assert raw.quantity_affected is None and flag.candidates == ["20", "30"]


def test_two_items_are_ambiguous(snapshot):
    """Chairs and tables in one message: the item is not chosen."""
    raw = rule_based_extract("Maju here. 20 chairs and 4 tables will come on Friday.", snapshot, REPORTED_ON)
    flag = next(f for f in raw.flags if f.field == "resource_id")
    assert raw.resource_name is None and flag.reason == "ambiguous" and flag.candidates == ["R-01", "R-02"]


def test_shortfall_type(snapshot):
    """'cannot supply ... at all' is a shortfall, not a delay."""
    raw = rule_based_extract("Maju here, sorry we cannot supply the remaining 20 chairs at all.", snapshot, REPORTED_ON)
    assert raw.disruption_type.value == "supplier_shortfall"


def test_unclear_type_is_flagged(snapshot):
    """No date and no delay or shortfall words: the type is left for the owner."""
    raw = rule_based_extract("Maju here, question about the chairs.", snapshot, REPORTED_ON)
    assert raw.disruption_type is None and flags_by_field(raw)["type"] == "missing"


def test_raw_extraction_is_strict():
    """The model's reply shape rejects unknown keys and wrong types."""
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"supplier_name": "Maju", "confidence": 0.9})
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"quantity_affected": "twenty"})
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"new_arrival_date": "Friday"})
