# Integration Guide

For **Person 2** (backend), **Person 4** (recovery), **Person 5** (AI / evaluation).
Built against `CONTRACTS.md` v0.1 (copy in `docs/CONTRACTS_v0.1_reference.md`).

## 1. Where it plugs in

```python
from impact_engine import analyze_impact

result = analyze_impact(incident, snapshot)        # contract signature (section 5)
payload = result.to_contract()                     # JSON-ready, ONLY contract v0.1 fields
full = result.model_dump(mode="json")              # contract fields + extensions (section 3 below)
```

- `incident`: `NormalizedIncident` or a dict. `snapshot`: `BusinessSnapshot` or a raw dict (bad records are then rejected one by one and reported instead of failing the call).
- Optional extras: `config=SeverityConfig(...)`, `as_of=date` (defaults to the snapshot's `as_of`).
- Synchronous, deterministic, never raises for bad business data, never touches a database.

**Repo layout:** copy `impact_engine/` to `backend/scdc/impact/` (it uses relative imports only). Its `models.py`
mirrors the shared contract so the module runs alone; once `scdc.contracts` exists, replace the input models
(`Supplier, Resource, Delivery, Job, Commitment, Dependency, BusinessSnapshot, NormalizedIncident`) with imports
from it. The algorithm only reads the attributes listed in section 2.

## 2. Input fields the engine reads

| Record | Fields used |
|---|---|
| NormalizedIncident | `id`, `type` (only `supplier_delay`), `delivery_id`, `quantity_affected`, `new_arrival_date`, `unresolved_fields`; optional: `supplier_id`, `resource_id`, `original_arrival_date` (cross-checked against the delivery record) |
| BusinessSnapshot | `as_of`, `suppliers`, `resources`, `deliveries`, `jobs`, `commitments`, `dependencies`, `missing_or_stale` |
| Resource | `id`, `name`, `unit`, `on_hand_quantity` (`null` = not recorded), `on_hand_verified`, `reusable` |
| Delivery | `id`, `supplier_id`, `resource_id`, `quantity`, `expected_date`, `status` |
| Job | `id`, `name`, `event_date`, `priority` (`status` is read: `cancelled`/`completed` jobs are ignored) |
| Commitment | `id`, `job_id`, `reschedulable` |
| Dependency | all fields; `requires` edges carry `required_quantity` and `required_by` |

Supplier-to-delivery, delivery-to-resource and job-to-commitment links may be omitted from `dependencies`; the engine derives them (reported as `info`).

Inventory rule used (contract section 4): available on day *d* = `on_hand_quantity` + inbound deliveries expected strictly before *d*; jobs needing the resource on different days do not compete. Deliveries with status `delivered` or `cancelled` are ignored (already in on-hand / not coming).

## 3. Output

Contract v0.1 fields (as in `expected_impact.json`): `schema_version`, `disruption_id`, `affected_entities[]`
(`entity_type`, `entity_id`, `impact_status`, `severity` 0-10 int, `reason`, `dependency_path`, `evidence[{entity_id, fact}]`),
`checked_not_affected[]`, `resource_shortfalls[]` (`resource_id`, `date`, `required`, `available`, `shortfall`), `unresolved_facts[]`.

Additive **extensions** (not in v0.1; `to_contract()` removes them):

| Where | Field | Why it exists |
|---|---|---|
| result | `analysis_status` | `complete` / `partial` / `failed` (see section 5) |
| result | `data_issues[]` | rejected or contradictory records: `code`, `severity` (info/warning/error), `message`, `entity_id` |
| result | `as_of`, `config` | reproducibility |
| affected entity | `priority` | band of the score (`low`..`critical`); `null` when unresolved |
| affected entity | `severity_breakdown` | the three factors, weights, unrounded score, `assumed_factors` |
| affected entity | `dependency_paths` | ALL routes (`dependency_path` is the shortest) |
| affected entity | `missing_information[]` | the facts blocking this entity |
| checked_not_affected | `dependency_paths` | |

`unresolved_facts[]` item (v0.1 leaves the shape open; **proposed for v1.0**):
`{entity_id, field, reason (missing|ambiguous|unmatched|conflicting|unverified), note, affects[]}`.

### Real output (`python -m impact_engine --contract`, abridged)

```json
{
  "schema_version": "1.0",
  "disruption_id": "D-001",
  "affected_entities": [
    {"entity_type": "resource", "entity_id": "R-01", "impact_status": "confirmed", "severity": 6,
     "reason": "Only 50 chairs available on 2026-10-22 against 70 required.",
     "dependency_path": ["S-01", "DL-01", "R-01"],
     "evidence": [{"entity_id": "R-01", "fact": "on_hand_quantity=30"},
                  {"entity_id": "DL-01", "fact": "only 20 of 40 arrive by 2026-10-21; 20 of 40 delayed from 2026-10-21 to 2026-10-23"}]},
    {"entity_type": "job", "entity_id": "J-01", "impact_status": "confirmed", "severity": 6,
     "reason": "Shared Folding Chairs pool short by 20 on 2026-10-22; J-01 requires 50.",
     "dependency_path": ["S-01", "DL-01", "R-01", "J-01"],
     "evidence": [{"entity_id": "DEP-03", "fact": "required_quantity=50, required_by=2026-10-22"}, "..."]}
  ],
  "checked_not_affected": [
    {"entity_type": "job", "entity_id": "J-03", "reason": "Needed 2026-10-25; the delayed 20 chairs arrive 2026-10-23, so 70 are available against 15 required."},
    {"entity_type": "commitment", "entity_id": "CM-03", "reason": "J-03 not affected."}
  ],
  "resource_shortfalls": [{"resource_id": "R-01", "date": "2026-10-22", "required": 70, "available": 50, "shortfall": 20}],
  "unresolved_facts": []
}
```

## 4. Status definitions

| `impact_status` | Meaning | Planner should... |
|---|---|---|
| `confirmed` | Recorded numbers prove the pool is short | generate recovery options; this is a fact |
| `potential_risk` | Could be hurt; a fact is uncertain (unknown arrival date, unverified stock, unknown competing demand) | plan, but treat the plan as `needs_confirmation` |
| `unresolved` | Data missing/contradictory; `severity` is `null` | ask the owner for the facts listed in `unresolved_facts` |

Items in `checked_not_affected` need no recovery. Commitments take the worst status of their job(s).

## 5. Error handling

| Situation | Result |
|---|---|
| Invalid incident (negative quantity, bad date, not a dict), unknown `delivery_id`, incident contradicting the delivery record (resource/supplier mismatch), delivery already delivered/cancelled, ambiguous or missing delivery, unsupported incident type | `analysis_status = failed`, no entities, `data_issues` (+ `unresolved_facts`) explain why. Backend: map to a 422-style `VALIDATION_ERROR` / `INVALID_STATE_TRANSITION` with `data_issues` as `details`. |
| A record fails validation (negative quantity, empty id, wrong type) | record skipped, `invalid_record` error, result `partial` |
| Duplicate id, dangling reference, wrong edge direction | record skipped, error issue, `partial` |
| Conflicting required quantity/date for the same resource and job | warning; the job is `unresolved` |
| No on-hand figure; delay larger than the delivery; non-reusable resource; partially delivered delivery | exposed jobs and the resource become `unresolved` |
| `date_conflict`: resource needed after the event, or commitment due before the resource is needed | warning (dependency's `required_by` stays authoritative) |
| Unknown arrival date / unverified stock / unknown competing demand | `potential_risk` plus an `unresolved_facts` entry |

**`partial` means "some information was missing or rejected".** In a `partial` result, absence from
`affected_entities` is not proof an entity is safe; show `data_issues` and `unresolved_facts` to the owner.
`complete` is returned only when there are no warnings, errors or unresolved facts (info notes are allowed).

## 6. Notes per teammate

**Person 4 (recovery)**
- Plan from `affected_entities` with `confirmed`/`potential_risk`; use `resource_shortfalls` for the quantity to cover (`required`, `available`, `shortfall`, `date`) and `dependency_paths` instead of re-walking the graph.
- `reschedulable` shows as evidence on commitments (`reschedulable=false`).
- The engine does not decide who gets scarce stock; both jobs are flagged. The shortfall factor in the score is the pool ratio for that reason.

**Person 5 (AI / evaluation)**
- Feed `reason`, `evidence` and `missing_information` to the explanation prompt; never let the model change `impact_status`, `severity` or any number.
- If extraction cannot match a field, put it in `NormalizedIncident.unresolved_fields`; the engine treats it as unknown rather than trusting the value.
- Reference answers for evaluation: `fixtures/demo/expected_impact.json`; `python -m pytest` asserts them.

**Person 2 (backend)**
- `GET /disruptions/{id}/impact` can return `result.to_contract()` (plus `analysis_status` / `data_issues` if the UI should show them).
- Re-run the analysis whenever records change; the output is deterministic for the same incident, snapshot and `as_of`.

## 7. Questions / proposals for the contract (for the Phase 1 review)

1. **Extension fields** (section 3): adopt them in v1.0, or stay strict and ignore them? The engine supports both.
2. **`unresolved_facts` shape**: proposal above.
3. **Failure reporting**: v0.1 has no way for the impact step to say "could not analyse". Proposal: `analysis_status` + `data_issues`.
4. **Open decision 3 (shared pool)**: implemented as proposed (both jobs `confirmed`, reason "Shared ... pool short by N").
5. **Severity values**: the engine gives 6 / 6 for J-01 / J-02 versus the illustrative 8 / 7 in `expected_impact.json`. Tests assert status, path and shortfall only, as the file's note says.
6. **Not modelled** (would need contract support): job-to-job dependencies, non-reusable stock, multi-day jobs, `supplier_shortfall` / `resource_unavailable` / `staff_absence` incidents.
