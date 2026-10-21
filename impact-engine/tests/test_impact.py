"""Known-answer tests for the impact engine on the team's contract (CONTRACTS v0.1).

Reference numbers (fixtures/demo, as_of 2026-10-20):
  DL-01: 40 chairs due 21 Oct; 20 of them slip to 23 Oct.
  J-01 (50) + J-02 (20) both need chairs on 22 Oct  -> demand 70
  supply on 22 Oct = 30 on hand + 20 arriving 21 Oct = 50 (was 70 without the delay) -> short 20
  J-03 needs 15 on 25 Oct; by then all 40 have arrived (70 available) -> not affected
"""
from datetime import date

import pytest

from impact_engine import (AnalysisStatus, BusinessSnapshot, ImpactStatus, NormalizedIncident, SeverityConfig,
                           analyze_impact, snapshot_from_raw)
from impact_engine.models import EntityType, ImpactResult, IssueCode, UnresolvedReason
from impact_engine.scenarios import add_dependency, demo_incident, expected_impact, find_record, seed_records

C, P, U = ImpactStatus.CONFIRMED, ImpactStatus.POTENTIAL_RISK, ImpactStatus.UNRESOLVED


def run(records=None, incident=None, config=None, as_of=None):
    return analyze_impact(incident if incident is not None else demo_incident(),
                          records if records is not None else seed_records(), config, as_of)


def affected(result, entity_id):
    matches = [e for e in result.affected_entities if e.entity_id == entity_id]
    assert len(matches) <= 1, f"{entity_id} appears {len(matches)} times in affected_entities"
    return matches[0] if matches else None


def cleared(result, entity_id):
    return next((c for c in result.checked_not_affected if c.entity_id == entity_id), None)


def codes(result):
    return {i.code for i in result.data_issues}


def fact(result, entity_id, field):
    return next((f for f in result.unresolved_facts if f.entity_id == entity_id and f.field == field), None)


def all_ids(result):
    return ({e.entity_id for e in result.affected_entities} | {c.entity_id for c in result.checked_not_affected})


# --------------------------------------------------------------------------- #
# The team's own expected result
# --------------------------------------------------------------------------- #
def test_matches_team_expected_impact_fixture():
    expected, r = expected_impact(), run()
    got = {(e.entity_type.value, e.entity_id): e for e in r.affected_entities}
    want = {(e["entity_type"], e["entity_id"]): e for e in expected["affected_entities"]}
    assert set(got) == set(want)
    for key, exp in want.items():
        assert got[key].impact_status.value == exp["impact_status"], key
        assert got[key].dependency_path == exp["dependency_path"], key
    assert {(c.entity_type.value, c.entity_id) for c in r.checked_not_affected} == \
           {(c["entity_type"], c["entity_id"]) for c in expected["checked_not_affected"]}
    assert [s.model_dump(mode="json") for s in r.resource_shortfalls] == expected["resource_shortfalls"]
    assert r.unresolved_facts == [] and expected["unresolved_facts"] == []
    assert (r.disruption_id, r.schema_version) == (expected["disruption_id"], expected["schema_version"])
    assert r.analysis_status is AnalysisStatus.COMPLETE and r.data_issues == []


def test_contract_output_contains_only_contract_fields():
    out = run().to_contract()
    assert set(out) == {"schema_version", "disruption_id", "affected_entities", "checked_not_affected",
                        "resource_shortfalls", "unresolved_facts"}
    for e in out["affected_entities"]:
        assert set(e) == {"entity_type", "entity_id", "impact_status", "severity", "reason", "dependency_path", "evidence"}
        assert isinstance(e["severity"], int) and 0 <= e["severity"] <= 10
        assert e["evidence"] and all(set(ev) == {"entity_id", "fact"} for ev in e["evidence"])
    assert all(set(c) == {"entity_type", "entity_id", "reason"} for c in out["checked_not_affected"])


# --------------------------------------------------------------------------- #
# Directly affected and multiple downstream events
# --------------------------------------------------------------------------- #
def test_main_scenario_numbers_and_downstream_commitments():
    r = run()
    assert [(s.date.isoformat(), s.required, s.available, s.shortfall) for s in r.resource_shortfalls] == \
           [("2026-10-22", 70, 50, 20)]
    for job_id in ("J-01", "J-02"):
        assert affected(r, job_id).impact_status is C
    cm1 = affected(r, "CM-01")
    assert cm1.dependency_path == ["S-01", "DL-01", "R-01", "J-01", "CM-01"]
    assert cm1.severity == affected(r, "J-01").severity            # commitments inherit their job's score
    assert any(ev.fact == "reschedulable=false" for ev in cm1.evidence)
    assert affected(r, "R-01").impact_status is C and affected(r, "R-01").dependency_path == ["S-01", "DL-01", "R-01"]


def test_higher_priority_job_scores_at_least_as_high():
    r = run()
    assert affected(r, "J-01").severity >= affected(r, "J-02").severity       # high vs medium priority
    assert affected(r, "J-01").severity_breakdown.score == pytest.approx(6.1)  # 10*(0.4*.857+0.4*.286+0.2*.75)


def test_single_directly_affected_job():
    records = seed_records()
    find_record(records, "dependencies", "DEP-03")["required_quantity"] = 60       # J-01 now needs 60
    find_record(records, "jobs", "J-02").update(event_date="2026-10-26", deadline="2026-10-26")
    find_record(records, "dependencies", "DEP-04")["required_by"] = "2026-10-26"
    find_record(records, "commitments", "CM-02")["required_date"] = "2026-10-26"
    r = run(records)
    assert {e.entity_id for e in r.affected_entities if e.entity_type is EntityType.JOB} == {"J-01"}
    assert [(s.required, s.available, s.shortfall) for s in r.resource_shortfalls] == [(60, 50, 10)]
    assert cleared(r, "J-02") is not None


def test_a_delivery_arriving_on_the_needed_day_does_not_count_for_that_day():
    """CONTRACTS section 4: available on day d counts deliveries expected strictly BEFORE d."""
    incident = demo_incident()
    incident["new_arrival_date"] = "2026-10-22"       # the 20 chairs arrive the same day the events need them
    r = run(incident=incident)
    assert affected(r, "J-01").impact_status is C
    assert [(s.available, s.shortfall) for s in r.resource_shortfalls] == [(50, 20)]
    incident["new_arrival_date"] = "2026-10-21"       # ...but a delivery on the original day is not a delay at all
    assert run(incident=incident).affected_entities == []


def test_pool_that_was_already_short_before_the_delay_reports_both_numbers():
    records = seed_records()
    find_record(records, "dependencies", "DEP-03")["required_quantity"] = 80      # demand 100 vs 70 before the delay
    r = run(records)
    assert [(s.required, s.available, s.shortfall) for s in r.resource_shortfalls] == [(100, 50, 50)]
    assert any("would still be 30" in ev.fact for ev in affected(r, "J-01").evidence)
    assert affected(r, "J-01").impact_status is C


def test_job_needing_chairs_after_all_units_arrive_is_cleared_with_numbers():
    r = run()
    assert affected(r, "J-03") is None
    assert "70 are available against 15 required" in cleared(r, "J-03").reason


def test_other_deliveries_of_same_resource_count_and_are_not_disrupted():
    records = seed_records()
    records["deliveries"].append({"id": "DL-02", "supplier_id": "S-01", "resource_id": "R-01",
                                  "quantity": 10, "expected_date": "2026-10-21", "status": "scheduled"})
    r = run(records)
    assert [(s.available, s.shortfall) for s in r.resource_shortfalls] == [(60, 10)]   # 30 + 20 + 10
    assert not any("DL-02" in p for e in r.affected_entities for p in e.dependency_paths)
    assert r.analysis_status is AnalysisStatus.COMPLETE   # derived edges are INFO only


# --------------------------------------------------------------------------- #
# Spare inventory prevents an impact (and the boundary cases)
# --------------------------------------------------------------------------- #
def test_spare_inventory_prevents_impact():
    records = seed_records()
    find_record(records, "resources", "R-01")["on_hand_quantity"] = 60       # 60 + 20 = 80 >= 70
    r = run(records)
    assert r.affected_entities == [] and r.resource_shortfalls == []
    assert r.analysis_status is AnalysisStatus.COMPLETE
    assert "spare 10" in cleared(r, "J-01").reason
    assert cleared(r, "R-01") is not None and cleared(r, "CM-01") is not None


def test_exactly_enough_stock_is_not_an_impact():
    records = seed_records()
    find_record(records, "resources", "R-01")["on_hand_quantity"] = 50       # 50 + 20 = 70 = demand
    assert run(records).affected_entities == []


def test_one_unit_short_is_an_impact():
    records = seed_records()
    find_record(records, "resources", "R-01")["on_hand_quantity"] = 49
    r = run(records)
    assert affected(r, "J-01").impact_status is C and r.resource_shortfalls[0].shortfall == 1


def test_cancelled_job_does_not_compete_for_stock():
    records = seed_records()
    find_record(records, "jobs", "J-02")["status"] = "cancelled"              # demand drops to 50 = supply
    r = run(records)
    assert r.affected_entities == [] and cleared(r, "J-02") is not None


# --------------------------------------------------------------------------- #
# Unrelated events must not be flagged
# --------------------------------------------------------------------------- #
def test_unrelated_job_and_resource_are_never_flagged():
    records = seed_records()
    records["jobs"].append({"id": "J-04", "name": "Garden party", "event_date": "2026-10-22",
                            "deadline": "2026-10-22", "status": "scheduled", "priority": "high"})
    records["commitments"].append({"id": "CM-04", "job_id": "J-04", "commitment_type": "event_setup",
                                   "required_date": "2026-10-22", "reschedulable": False, "status": "active"})
    add_dependency(records, "DEP-20", ("resource", "R-02"), ("job", "J-04"), "requires", 2, "2026-10-22")
    add_dependency(records, "DEP-21", ("job", "J-04"), ("commitment", "CM-04"), "fulfils")
    r = run(records)
    assert not {"J-04", "CM-04", "R-02", "S-02", "S-03"} & all_ids(r)
    # J-01 also needs 6 tables (R-02, DEP-06) but tables are not disrupted
    assert not any("R-02" in p or "DEP-06" in ev.entity_id for e in r.affected_entities for p in e.dependency_paths for ev in e.evidence)


# --------------------------------------------------------------------------- #
# Missing / unverified / unknown information
# --------------------------------------------------------------------------- #
def test_missing_on_hand_is_unresolved_not_guessed():
    records = seed_records()
    find_record(records, "resources", "R-01")["on_hand_quantity"] = None
    r = run(records)
    assert r.analysis_status is AnalysisStatus.PARTIAL
    for entity_id in ("R-01", "J-01", "J-02", "CM-01", "CM-02"):
        e = affected(r, entity_id)
        assert e.impact_status is U and e.severity is None and e.priority is None, entity_id
    f = fact(r, "R-01", "on_hand_quantity")
    assert f.reason is UnresolvedReason.MISSING and set(f.affects) == {"J-01", "J-02"}
    assert cleared(r, "J-03") is not None            # outside the delay window; stock count is irrelevant
    assert r.resource_shortfalls == []


def test_unknown_arrival_date_gives_potential_risk_not_confirmed():
    incident = demo_incident()
    incident["new_arrival_date"] = None
    r = run(incident=incident)
    for entity_id in ("R-01", "J-01", "J-02", "CM-01", "CM-02"):
        assert affected(r, entity_id).impact_status is P, entity_id
    assert affected(r, "J-01").severity is not None
    assert fact(r, "D-001", "new_arrival_date").reason is UnresolvedReason.MISSING
    assert cleared(r, "J-03") is not None            # 15 needed vs 50 even if the 20 never come


def test_unverified_stock_count_downgrades_confirmed_to_potential():
    records = seed_records()
    find_record(records, "resources", "R-01")["on_hand_verified"] = False
    r = run(records)
    assert affected(r, "J-01").impact_status is P and "not been verified" in affected(r, "J-01").reason
    assert fact(r, "R-01", "on_hand_quantity").reason is UnresolvedReason.UNVERIFIED
    assert [s.shortfall for s in r.resource_shortfalls] == [20]   # the arithmetic is still reported


def test_incident_fields_listed_as_unresolved_are_treated_as_unknown():
    incident = demo_incident()
    incident["unresolved_fields"] = [{"field": "quantity_affected", "reason": "ambiguous", "raw_value": "some chairs",
                                      "candidates": [], "note": "message said 'some'"}]
    r = run(incident=incident)                       # quantity_affected=20 is present but unverified
    assert affected(r, "J-01").impact_status is U
    assert fact(r, "D-001", "quantity_affected").reason is UnresolvedReason.AMBIGUOUS


def test_unknown_demand_gives_unresolved_job_and_potential_neighbour():
    records = seed_records()
    find_record(records, "dependencies", "DEP-04")["required_quantity"] = None   # J-02 demand unknown
    r = run(records)
    assert affected(r, "J-02").impact_status is U
    j1 = affected(r, "J-01")
    assert j1.impact_status is P and "J-02" in j1.reason        # 50 fits in 50, but J-02 is unknown
    assert j1.severity_breakdown.assumed_factors == ["resource_shortfall"]
    assert affected(r, "R-01").impact_status is P and r.resource_shortfalls == []


def test_snapshot_missing_or_stale_items_are_surfaced():
    records = seed_records()
    records["missing_or_stale"] = [{"entity_id": "R-01", "field": "on_hand_quantity", "reason": "unverified",
                                    "note": "count is two weeks old"}]
    r = run(records)
    assert fact(r, "R-01", "on_hand_quantity").note == "count is two weeks old"
    assert IssueCode.STALE_OR_MISSING in codes(r) and r.analysis_status is AnalysisStatus.PARTIAL


# --------------------------------------------------------------------------- #
# Duplicate dependency paths
# --------------------------------------------------------------------------- #
def test_entity_reached_by_two_routes_appears_once_with_both_paths():
    records = seed_records()
    add_dependency(records, "DEP-10", ("job", "J-02"), ("commitment", "CM-01"), "fulfils")   # CM-01 needs both jobs
    r = run(records)
    cm1 = affected(r, "CM-01")                       # asserts it appears only once
    assert cm1.impact_status is C
    assert cm1.dependency_paths == [["S-01", "DL-01", "R-01", "J-01", "CM-01"],
                                    ["S-01", "DL-01", "R-01", "J-02", "CM-01"]]
    assert cm1.dependency_path == cm1.dependency_paths[0]
    keys = [(e.entity_type, e.entity_id) for e in r.affected_entities] + \
           [(c.entity_type, c.entity_id) for c in r.checked_not_affected]
    assert len(keys) == len(set(keys))


def test_commitment_takes_worst_status_of_its_jobs():
    records = seed_records()
    add_dependency(records, "DEP-10", ("job", "J-03"), ("commitment", "CM-01"), "fulfils")   # J-03 is not affected
    r = run(records)
    assert affected(r, "CM-01").impact_status is C and "J-03" not in affected(r, "CM-01").reason


def test_identical_duplicate_dependency_is_merged_quietly():
    records = seed_records()
    add_dependency(records, "DEP-99", ("resource", "R-01"), ("job", "J-02"), "requires", 20, "2026-10-22")
    r = run(records)
    assert IssueCode.DUPLICATE_DEPENDENCY in codes(r)
    assert affected(r, "J-02").impact_status is C and r.analysis_status is AnalysisStatus.COMPLETE


def test_missing_dependency_records_are_derived_from_delivery_and_commitment():
    records = seed_records()
    records["dependencies"] = [d for d in records["dependencies"] if d["id"] not in ("DEP-01", "DEP-02", "DEP-07")]
    r = run(records)
    assert affected(r, "CM-01").dependency_path == ["S-01", "DL-01", "R-01", "J-01", "CM-01"]
    assert IssueCode.DERIVED_EDGE in codes(r) and r.analysis_status is AnalysisStatus.COMPLETE


# --------------------------------------------------------------------------- #
# Conflicting or invalid data
# --------------------------------------------------------------------------- #
def test_invalid_record_is_rejected_and_reported_not_silently_ignored():
    records = seed_records()
    find_record(records, "dependencies", "DEP-04")["required_quantity"] = -5
    r = run(records)                                 # must not raise
    assert IssueCode.INVALID_RECORD in codes(r)
    assert any(i.entity_id == "DEP-04" for i in r.data_issues)
    assert r.analysis_status is AnalysisStatus.PARTIAL     # a gap in the data is never labelled COMPLETE


def test_record_with_empty_id_is_rejected_and_rest_still_analysed():
    records = seed_records()
    records["jobs"].append({"id": "", "name": "Ghost", "event_date": "2026-10-22"})
    r = run(records)
    assert IssueCode.INVALID_RECORD in codes(r) and affected(r, "J-01").impact_status is C


def test_conflicting_required_quantities_make_the_job_unresolved():
    records = seed_records()
    add_dependency(records, "DEP-99", ("resource", "R-01"), ("job", "J-02"), "requires", 25, "2026-10-22")  # DEP-04: 20
    r = run(records)
    assert IssueCode.CONFLICTING_DEPENDENCY in codes(r)
    assert affected(r, "J-02").impact_status is U
    assert fact(r, "R-01->J-02", "required_quantity").reason is UnresolvedReason.CONFLICTING
    assert affected(r, "J-01").impact_status is P


def test_delayed_quantity_larger_than_the_delivery_is_unresolved():
    incident = demo_incident()
    incident["quantity_affected"] = 50                # DL-01 is only 40
    r = run(incident=incident)
    assert IssueCode.CONFLICTING_DATA in codes(r)
    assert affected(r, "J-01").impact_status is U
    assert fact(r, "DL-01", "quantity").reason is UnresolvedReason.CONFLICTING


def test_dangling_reference_is_reported_and_analysis_continues():
    records = seed_records()
    add_dependency(records, "DEP-99", ("resource", "R-01"), ("job", "J-99"), "requires", 10, "2026-10-22")
    r = run(records)
    assert IssueCode.DANGLING_REFERENCE in codes(r) and affected(r, "J-01").impact_status is C


def test_wrong_edge_direction_is_rejected():
    records = seed_records()
    add_dependency(records, "DEP-99", ("job", "J-01"), ("resource", "R-01"), "requires", 10, "2026-10-22")
    assert IssueCode.INVALID_DEPENDENCY in codes(run(records))


def test_duplicate_entity_id_is_reported_and_first_record_wins():
    records = seed_records()
    records["jobs"].append({"id": "J-01", "name": "Impostor", "event_date": "2026-10-30"})
    r = run(records)
    assert IssueCode.DUPLICATE_ID in codes(r) and affected(r, "J-01").impact_status is C


def test_incident_date_that_disagrees_with_the_delivery_record_is_flagged():
    incident = demo_incident()
    incident["original_arrival_date"] = "2026-10-22"  # record says 21 Oct
    r = run(incident=incident)
    assert IssueCode.CONFLICTING_DATA in codes(r) and affected(r, "J-01").impact_status is C   # record used


def test_resource_required_after_its_job_takes_place_is_flagged():
    records = seed_records()
    find_record(records, "dependencies", "DEP-03")["required_by"] = "2026-10-23"   # J-01 is on 22 Oct
    assert IssueCode.DATE_CONFLICT in codes(run(records))


def test_commitment_due_before_resource_is_needed_is_flagged():
    records = seed_records()
    find_record(records, "commitments", "CM-01")["required_date"] = "2026-10-21"
    assert IssueCode.DATE_CONFLICT in codes(run(records))


def test_non_reusable_resource_is_unresolved_because_depletion_is_not_modelled():
    records = seed_records()
    find_record(records, "resources", "R-01")["reusable"] = False
    assert affected(run(records), "J-01").impact_status is U


def test_partially_delivered_delivery_blocks_the_calculation():
    records = seed_records()
    records["deliveries"].append({"id": "DL-02", "supplier_id": "S-02", "resource_id": "R-01", "quantity": 10,
                                  "expected_date": "2026-10-21", "status": "partially_delivered"})
    r = run(records)
    assert affected(r, "J-01").impact_status is U and fact(r, "DL-02", "quantity") is not None


# --------------------------------------------------------------------------- #
# Unusable incidents fail cleanly (no exceptions)
# --------------------------------------------------------------------------- #
def test_invalid_incident_fails_cleanly():
    incident = demo_incident()
    incident["quantity_affected"] = -20
    r = run(incident=incident)
    assert r.analysis_status is AnalysisStatus.FAILED and r.affected_entities == []
    assert IssueCode.INVALID_INCIDENT in codes(r) and r.disruption_id == "D-001"


@pytest.mark.parametrize("change,code", [
    ({"delivery_id": "DL-404"}, IssueCode.UNKNOWN_ENTITY),
    ({"resource_id": "R-02"}, IssueCode.CONFLICTING_DATA),       # DL-01 supplies R-01
    ({"supplier_id": "S-02"}, IssueCode.CONFLICTING_DATA),       # DL-01 comes from S-01
    ({"type": "staff_absence"}, IssueCode.UNSUPPORTED_INCIDENT_TYPE),
])
def test_incident_that_contradicts_the_records_fails_cleanly(change, code):
    r = run(incident={**demo_incident(), **change})
    assert r.analysis_status is AnalysisStatus.FAILED and code in codes(r) and r.affected_entities == []


def test_delivery_that_has_already_arrived_cannot_be_delayed():
    records = seed_records()
    find_record(records, "deliveries", "DL-01")["status"] = "delivered"
    assert run(records).analysis_status is AnalysisStatus.FAILED


def test_garbage_inputs_do_not_raise():
    assert analyze_impact(None, seed_records()).analysis_status is AnalysisStatus.FAILED          # type: ignore[arg-type]
    assert analyze_impact(demo_incident(), 123).analysis_status is AnalysisStatus.FAILED          # type: ignore[arg-type]


def test_missing_delivery_id_uses_the_only_matching_delivery():
    incident = demo_incident()
    incident["delivery_id"] = None
    r = run(incident=incident)
    assert affected(r, "J-01").impact_status is C and r.analysis_status is AnalysisStatus.COMPLETE


def test_ambiguous_delivery_fails_and_asks_for_clarification():
    records = seed_records()
    records["deliveries"].append({"id": "DL-02", "supplier_id": "S-01", "resource_id": "R-01", "quantity": 10,
                                  "expected_date": "2026-10-21", "status": "scheduled"})
    incident = demo_incident()
    incident["delivery_id"] = None
    r = run(records, incident)
    assert r.analysis_status is AnalysisStatus.FAILED
    assert fact(r, "D-001", "delivery_id").reason is UnresolvedReason.AMBIGUOUS


@pytest.mark.parametrize("change", [{"new_arrival_date": "2026-10-21"}, {"quantity_affected": 0}])
def test_a_delay_that_moves_nothing_affects_nothing(change):
    r = run(incident={**demo_incident(), **change})
    assert r.affected_entities == [] and cleared(r, "J-01") is not None


# --------------------------------------------------------------------------- #
# Severity, determinism, serialisation
# --------------------------------------------------------------------------- #
def test_severity_weights_are_configurable_and_echoed():
    urgent_only = SeverityConfig(weight_deadline_urgency=1, weight_resource_shortfall=0, weight_commitment_importance=0)
    r = run(config=urgent_only)
    assert affected(r, "J-01").severity == 9                         # 10 * urgency(0.857) = 8.6
    assert r.config.weight_deadline_urgency == 1


def test_more_distant_need_lowers_urgency_and_severity():
    near, far = run(), run(as_of=date(2026, 10, 10))                 # needed 12 days later -> urgency 0.143
    assert far.affected_entities[1].severity_breakdown.deadline_urgency == pytest.approx(0.143, abs=1e-3)
    assert far.affected_entities[1].severity < near.affected_entities[1].severity


@pytest.mark.parametrize("bad", [
    dict(weight_deadline_urgency=0, weight_resource_shortfall=0, weight_commitment_importance=0),
    dict(threshold_medium=9, threshold_high=5, threshold_critical=7.5),
    dict(weight_resource_shortfall=-1),
    dict(priority_importance={"high": 2.0}),
])
def test_invalid_severity_config_is_rejected(bad):
    with pytest.raises(ValueError):
        SeverityConfig(**bad)


def test_analysis_is_deterministic():
    assert run().model_dump(mode="json") == run().model_dump(mode="json")


def test_result_round_trips_through_json():
    r = run()
    assert ImpactResult.model_validate_json(r.model_dump_json()) == r


def test_accepts_models_or_dicts_and_does_not_mutate_inputs():
    snapshot, incident = snapshot_from_raw(seed_records()), NormalizedIncident.model_validate(demo_incident())
    before = (snapshot.model_dump(), incident.model_dump())
    from_models = analyze_impact(incident, snapshot)
    assert (snapshot.model_dump(), incident.model_dump()) == before
    assert from_models.model_dump() == run().model_dump()
    assert isinstance(snapshot, BusinessSnapshot)
