# Impact Analysis Engine (Person 3)

Answers one question: **when something goes wrong, which commitments are actually in trouble, and why?**

It implements `analyze_impact(incident, snapshot) -> ImpactResult` exactly as defined in the team's
`CONTRACTS.md` v0.1 (section 5 and 6.3). It is a pure function: no database, no HTTP, no AI. It runs and
is tested on its own, using the team's demo fixtures.

> AI proposes; deterministic logic verifies; humans authorize. Everything in this module is deterministic.
> It decides what depends on what and whether the numbers add up. An AI model may later *explain* the
> output but never changes it.

---

## Run it

Python 3.10+.

```bash
pip install -r requirements.txt          # pydantic + pytest

python -m impact_engine                  # the demo incident D-001 (readable report)
python -m impact_engine --contract       # JSON with ONLY contract v0.1 fields
python -m impact_engine --json           # JSON including extension fields

python -m impact_engine --scenario spare_inventory
python -m impact_engine --scenario missing_on_hand
python -m impact_engine --scenario unverified_stock
python -m impact_engine --scenario unknown_arrival
python -m impact_engine --scenario conflicting_data

python -m pytest -q                      # 56 tests, including a comparison with expected_impact.json
```

## Layout

```
impact_engine/
  analyzer.py    the algorithm: analyze_impact(...)
  models.py      typed input + output models (mirror CONTRACTS sections 3, 4, 6.1, 6.3)
  config.py      severity weights and thresholds (configurable)
  loader.py      raw dict -> BusinessSnapshot, rejecting bad records one at a time
  validation.py  cross-record checks: duplicates, dangling refs, conflicts, date contradictions
  graph.py       dependency graph + path enumeration
  scenarios.py   loads the team fixtures; named demo variations
  report.py      plain-text report
fixtures/demo/   seed.json, incident.json, expected_impact.json  (copied from the team)
tests/test_impact.py
docs/INTEGRATION.md          what Persons 2, 4, 5 need to know
docs/CONTRACTS_v0.1_reference.md
```

## The graph model (CONTRACTS section 4)

```
Supplier --ships--> Delivery --supplies--> Resource --requires--> Job --fulfils--> Commitment
  S-01               DL-01                   R-01       (qty, by)    J-01           CM-01
```

Reaching a node does **not** mean it is hurt. It means the node must be checked against the numbers.

## The algorithm (stage numbers follow the brief)

1. **Build the graph** from the dependency records. Links the dependency table forgot (supplier->delivery, delivery->resource, job->commitment) are derived from the delivery/commitment records and reported as `info`.
2. **Identify the directly affected entity**: the delayed delivery, its supplier and its resource.
3. **Traverse** downstream. The supplier is only followed to the *incident's* delivery, not everything it ships.
4. **Deduplicate, keep every path.** An entity reached by several routes appears once, with all routes in `dependency_paths`.
5. **Check quantities** with the contract's inventory rule: a reusable resource is occupied only on the day a job needs it, so jobs needing it on *different* days do not compete. Available on day *d* = `on_hand_quantity` + deliveries expected **strictly before** *d*. The incident moves `quantity_affected` units of one delivery from its original date to `new_arrival_date`; the engine computes supply with and without that move.
6. **Check dates**: the delay only matters for days *d* with `original_date < d <= new_arrival_date` (the delay window). Jobs needing the resource outside the window are cleared, with the numbers.
7. **Classify** each entity (below).
8. **Score severity** (below).
9. **Explain**: every result carries a `reason` and `evidence` items (`{entity_id, fact}`) containing the exact numbers.
10. **Return** an `ImpactResult`.

Demo walk-through (D-001): on 22 Oct, supply is 30 on hand + 20 arriving 21 Oct = **50** (it would have been 70). J-01 (50) + J-02 (20) need **70**, so the pool is short by **20**. J-01, J-02, their commitments and R-01 are `confirmed`. J-03 needs 15 on 25 Oct, when all 40 chairs have arrived (70 available), so it is cleared. Tables (R-02) are never touched.

## Impact statuses (contract enum)

| Status | Meaning |
|---|---|
| `confirmed` | The recorded numbers prove a shortfall. |
| `potential_risk` | Could be hurt but a fact is uncertain: unknown arrival date, unverified stock count, or unknown demand from a competing job. |
| `unresolved` | Cannot decide: data missing or contradictory (no on-hand figure, conflicting quantities, delay larger than the delivery...). No score is produced. |

Entities verified safe go to `checked_not_affected`. Entities the graph never reaches appear nowhere.

A commitment takes the worst status of the job(s) that fulfil it. The resource appears as an affected entity when
the jobs competing for it in the delay window are affected (this is what `expected_impact.json` shows).

## Severity (0-10 integer; the unrounded score is in `severity_breakdown`)

```
score = 10 x (w1*urgency + w2*shortfall + w3*importance) / (w1 + w2 + w3)

urgency    = 1 - clamp(days from as_of until the resource is needed / 14, 0, 1)
shortfall  = units short for the WHOLE pool that day / units the pool needs that day
importance = low 0.25 | medium 0.5 | high 0.75 | critical 1.0   (from Job.priority)
```

Defaults `w1 = 0.4, w2 = 0.4, w3 = 0.2`. Bands: `>= 7.5` critical, `>= 5` high, `>= 2.5` medium, else low.

Demo: J-01 = 10 x (0.4x0.857 + 0.4x0.286 + 0.2x0.75) = 6.1, so severity **6 (high)**; J-02 = 5.6, so **6**. A commitment copies its job's score; the resource takes the highest score among its jobs.

The shortfall factor is deliberately the **pool** ratio (20/70), not a per-job figure, because who receives the
scarce chairs is a recovery decision (Person 4), not something impact analysis should guess.

All numbers live in `SeverityConfig` and are echoed back in every result.

## Assumptions and known limitations

- **Weights are judgement calls.** The score is a ranking aid, not a measurement. Tune it with the owner.
- **Placeholder for unknowns.** When a factor cannot be measured the score uses `unknown_factor_default = 0.5` and lists it in `assumed_factors`. This can make a `potential_risk` score *higher* than a measured `confirmed` one (see `--scenario conflicting_data`). Check `assumed_factors` before trusting a ranking.
- **Shared shortfall is not attributed to one job.** Both competing jobs are flagged (contract open decision 3: "mark both confirmed"). Confirmed means the *pool* is short.
- **Day-level resolution only.** No hours, travel time or multi-day events.
- **Only recorded dependencies are seen.** A missing record means a missed impact. Any rejected record or warning makes the result `partial`, never `complete`, and in a `partial` result absence from the list is not proof of safety.
- **Supports `supplier_delay` only.** Other disruption types return `failed` with a clear message. `supplier_shortfall` (units never arrive) is a small extension of the same logic.
- **Non-reusable resources and partially delivered deliveries are not modelled**; they produce `unresolved` rather than a guess.
- **Job.deadline is not used.** `Dependency.required_by` is authoritative for when a resource is needed (it falls back to `Job.event_date`). Contradictions are flagged as `date_conflict`.
- `unresolved_fields` on the incident are treated as unknown even when a value is present.

## What the tests cover

| Required scenario | Tests |
|---|---|
| Team's expected result | `test_matches_team_expected_impact_fixture`, `test_contract_output_contains_only_contract_fields` |
| Directly affected event | `test_single_directly_affected_job` |
| Multiple downstream events | `test_main_scenario_numbers_and_downstream_commitments` |
| Spare inventory prevents impact | `test_spare_inventory_...`, `test_exactly_enough_...`, `test_one_unit_short_...` |
| Unrelated event not flagged | `test_unrelated_job_and_resource_are_never_flagged` |
| Missing availability | `test_missing_on_hand_...`, `test_unknown_arrival_...`, `test_unverified_stock_...`, `test_unknown_demand_...` |
| Duplicate dependency paths | `test_entity_reached_by_two_routes_appears_once_with_both_paths`, `test_identical_duplicate_dependency_...` |
| Conflicting / invalid data | invalid record, empty id, conflicting quantities, delay larger than delivery, dangling reference, wrong edge direction, duplicate id, date disagreements, invalid / contradictory / unsupported incident |
| The contract's stock rule | `test_a_delivery_arriving_on_the_needed_day_does_not_count_for_that_day` |
