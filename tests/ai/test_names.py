"""Tests for name matching: one block per rule agreed in step 2b."""

from __future__ import annotations

import pytest

from scdc.ai.names import norm, resolve_name, scan_for_names, singular

SUPPLIERS = {
    "S-01": ["Maju Rental Supplies", "Maju", "Maju Rental"],
    "S-02": ["Cahaya Event Rentals", "Cahaya"],
    "S-03": ["Delima Furniture Trading", "Delima"],
}
RESOURCES = {
    "R-01": ["Folding Chairs", "chairs", "chair", "kerusi", "kerusi lipat"],
    "R-02": ["Round Tables (10-seat)", "tables", "meja"],
}


@pytest.mark.parametrize("word, expected", [
    ("chairs", "chair"), ("tables", "table"), ("boxes", "box"), ("supplies", "supply"),
    ("glass", "glass"), ("bus", "bus"), ("chair", "chair"),
])
def test_singular(word, expected):
    """Simple plurals become singular; 'glass' and short words are left alone."""
    assert singular(word) == expected


def test_norm_ignores_case_punctuation_and_plurals():
    """'Chairs!' and 'chair' compare equal."""
    assert norm("Chairs!") == norm("chair") == "chair"


@pytest.mark.parametrize("text, entity", [
    ("Maju", "S-01"),
    ("MAJU RENTAL", "S-01"),
    ("maju rental supplies", "S-01"),
    ("Maju Rental here", "S-01"),          # contains an alias as whole words
    ("Cahaya Event", "S-02"),               # whole-word part of a name
    ("Delima.", "S-03"),
])
def test_supplier_names_match(text, entity):
    """Names, aliases and whole-word parts match, ignoring case and punctuation."""
    match = resolve_name(text, SUPPLIERS)
    assert match.status == "matched" and match.entity_id == entity


@pytest.mark.parametrize("text", ["chair", "Chairs", "folding chair", "kerusi lipat"])
def test_resource_names_match_including_plurals(text):
    """Singular and plural forms both reach R-01."""
    assert resolve_name(text, RESOURCES).entity_id == "R-01"


def test_plural_works_without_both_aliases():
    """'table' matches R-02 even though only 'tables' is an alias."""
    assert resolve_name("table", {"R-02": ["tables"]}).entity_id == "R-02"


def test_two_matches_are_ambiguous():
    """A name that fits two records is not matched; both are suggested."""
    match = resolve_name("Rental", SUPPLIERS)
    assert match.status == "ambiguous" and match.candidates == ["S-01", "S-02"]


@pytest.mark.parametrize("text, suggestion", [("chiars", "R-01"), ("Cahya", "S-02"), ("Delma", "S-03")])
def test_typos_are_suggested_not_matched(text, suggestion):
    """A close misspelling is never matched automatically, only suggested."""
    match = resolve_name(text, {**SUPPLIERS, **RESOURCES})
    assert match.status == "unmatched" and match.entity_id is None
    assert suggestion in match.candidates


def test_typo_next_to_a_correct_alias_still_matches():
    """'Maju Rentel' matches S-01 because it contains the correct alias 'Maju' as a whole word."""
    assert resolve_name("Maju Rentel", SUPPLIERS).entity_id == "S-01"


def test_unknown_name_is_unmatched_without_suggestions():
    """A name nothing like any record is unmatched with no suggestions."""
    match = resolve_name("Bintang Rentals", {"S-03": ["Delima Furniture Trading", "Delima"]})
    assert match.status == "unmatched" and match.candidates == []


def test_empty_name_is_unmatched():
    """No name means nothing to match."""
    assert resolve_name(None, SUPPLIERS).status == "unmatched"
    assert resolve_name("  ", SUPPLIERS).status == "unmatched"


def test_scan_finds_names_in_a_message():
    """The rule-based extractor finds which records a message mentions."""
    message = "Hi, Maju Rental here. The 20 chairs will come on Friday."
    assert scan_for_names(message, SUPPLIERS) == {"S-01": "Maju Rental"}
    assert scan_for_names(message, RESOURCES) == {"R-01": "chairs"}


def test_scan_finds_nothing_in_an_unrelated_message():
    """No known names, no matches."""
    assert scan_for_names("Hello, this is Bintang.", SUPPLIERS) == {}
