# AI Algorithm and Team Implementation Plan

## 1. Objective

Build a modular disruption-recovery pipeline that accepts an operational disruption, identifies affected business commitments, generates feasible recovery plans, explains the trade-offs, and waits for human approval.

The system should be divided into five workstreams that can be developed in parallel with agreed interfaces.

## 2. Overall Processing Pipeline

    Layer 1: Disruption Input
        |
        v
    Layer 2: Data Validation and Fact Extraction
        |
        v
    Layer 3: Business Context Retrieval
        |
        v
    Layer 4: Dependency and Impact Analysis
        |
        v
    Layer 5: Recovery Plan Generation
        |
        v
    Layer 6: Deterministic Feasibility Validation
        |
        v
    Layer 7: Plan Ranking and Explanation
        |
        v
    Layer 8: Human Approval
        |
        v
    Layer 9: Action Preparation and Audit Logging

Layers 1–3 prepare the information. Layers 4–7 determine and explain the consequences and options. Layers 8–9 control what happens next.

## 3. Detailed Algorithm

### Layer 1 — Disruption Input

**Purpose:** Receive a new incident from the user or a simulated integration.

Inputs:
- Disruption type.
- Description.
- Affected supplier, resource, or job.
- Reported time.
- Optional message text.

Example:

    Type: Supplier Delay
    Supplier: S-01
    Resource: Folding Chairs
    Quantity Affected: 20
    New Arrival Date: 2026-10-22

Processing:
1. Receive the structured form or sample message.
2. Assign a unique disruption ID.
3. Check that required fields are present.
4. Store the original report.
5. Pass the incident to validation and extraction.

Output:
- A stored incident record.
- A processing status.
- Validation errors, if any.

Fallback:
If message interpretation is uncertain, ask the user to complete or correct the structured form.

### Layer 2 — Data Validation and Fact Extraction

**Purpose:** Convert incoming information into a normalized, typed representation.

If the input is already structured, deterministic validation should be the default.

If the input is unstructured, an AI model may extract:
- Supplier name or ID.
- Resource name.
- Quantity affected.
- Original and revised dates.
- Reason for disruption.
- Confidence or ambiguity indicators.

Processing:
1. Parse the structured input.
2. If necessary, call the AI extraction adapter.
3. Require a predefined JSON schema.
4. Check data types, date formats, quantities, and required fields.
5. Resolve extracted names against known business records.
6. Mark unmatched or ambiguous values as unresolved.
7. Ask for correction when a material fact cannot be verified.

Important:
AI confidence scores are not proof that a fact is correct. Validate important extracted fields against business records or user confirmation.

Output:
A normalized incident object with validated fields and an explicit list of unresolved facts.

### Layer 3 — Business Context Retrieval

**Purpose:** Retrieve the minimum set of business records needed to analyze the incident.

Retrieve:
- Related supplier records.
- Affected resources and inventory.
- Jobs or events requiring those resources.
- Relevant deadlines and commitments.
- Dependencies connecting resources and jobs.
- Alternative suppliers or resources, if recorded.

Processing:
1. Start from the entities referenced by the incident.
2. Query related records.
3. Retrieve direct dependencies.
4. Expand to downstream commitments.
5. Deduplicate records.
6. Build a consistent snapshot for analysis.
7. Record which facts are missing or outdated.

Output:
A business-context snapshot containing relevant jobs, resources, suppliers, commitments, dependencies, and constraints.

Do not assume an alternative supplier is available just because it exists in the database. Availability must be represented and checked.

### Layer 4 — Dependency and Impact Analysis

**Purpose:** Identify direct and downstream consequences of the disruption.

Represent dependencies as a directed graph:

    Supplier Delivery
          |
          v
    Resource Availability
          |
          v
    Event Preparation
          |
          v
    Customer Commitment

Each edge represents a relationship that may transmit the impact.

Algorithm:
1. Create graph nodes for relevant entities.
2. Add dependency edges from stored business records.
3. Mark the disrupted entity.
4. Traverse outgoing dependency edges.
5. Collect reachable commitments and jobs.
6. Deduplicate affected entities.
7. Evaluate the conditions under which each entity is affected.
8. Calculate severity from urgency, quantity shortfall, and deadline exposure.
9. Classify each finding as confirmed impact, potential risk, or unresolved.
10. Produce an explanation for every finding.

A reachable node is not automatically confirmed to be affected. For example, a delayed delivery may not affect an event if enough spare inventory exists.

The impact engine must check quantities and actual dependency conditions.

Illustrative severity formula:

    Severity =
        w1 × DeadlineUrgency
      + w2 × ResourceShortfall
      + w3 × CommitmentImportance

Each input should be normalized to a documented scale. Weights are configuration values, not facts discovered by AI.

Output:
- Affected entities.
- Direct and indirect impact paths.
- Severity and priority.
- Evidence supporting each finding.
- Missing information that could change the result.

### Layer 5 — Recovery Plan Generation

**Purpose:** Generate candidate ways to resolve or reduce the impact.

Candidate actions may include:
- Use spare inventory.
- Source from an alternative supplier.
- Reallocate resources between jobs.
- Reschedule a job where the commitment permits it.
- Split a resource allocation.
- Ask the owner to contact the supplier for clarification.

Generation process:
1. Identify the shortage or disrupted dependency.
2. List available alternatives from business data.
3. Generate candidate actions using deterministic templates.
4. Optionally use AI to suggest additional candidates.
5. Convert every candidate into a structured action plan.
6. Attach assumptions and required information.
7. Remove duplicate candidates.

AI-generated candidates must refer to real, known entities wherever possible. A model must not invent suppliers, quantities, prices, or availability.

Output:
A list of candidate recovery plans, including their proposed actions and assumptions.

### Layer 6 — Deterministic Feasibility Validation

**Purpose:** Determine whether a candidate plan satisfies known operational constraints.

This is a critical non-AI layer.

For every plan, check:
- Resource availability.
- Quantity requirements.
- Supplier availability and lead time.
- Delivery dates.
- Job deadlines.
- Conflicts with other allocations.
- Dependency ordering.
- Required approvals or permissions.
- Whether the plan relies on unknown facts.

Algorithm:
1. Copy the relevant business snapshot.
2. Apply the proposed changes to a temporary plan state.
3. Check inventory and quantities.
4. Check supplier availability and timing.
5. Check each affected job's deadline.
6. Check that shared resources are not double-booked.
7. Check dependency and ordering rules.
8. Record each failed or unresolved constraint.
9. Return feasible, infeasible, or needs-confirmation.
10. Never mark a plan feasible merely because an AI model recommends it.

Use three explicit statuses:

- **FEASIBLE:** All required constraints pass using known data.
- **INFEASIBLE:** At least one hard constraint fails.
- **NEEDS_CONFIRMATION:** A material fact is missing or uncertain.

A plan that depends on unconfirmed supplier availability must not be presented as fully validated.

Output:
A validation result with status, passed checks, failed checks, and unresolved assumptions.

### Layer 7 — Plan Ranking and Explanation

**Purpose:** Compare validated plans and explain their trade-offs.

Possible ranking criteria:
- Number of commitments protected.
- Number of deadlines preserved.
- Additional cost, when reliable cost data exists.
- Number of operational changes required.
- Amount of unresolved uncertainty.

Process:
1. Exclude infeasible plans from the recommended set.
2. Separate plans needing confirmation.
3. Score feasible plans using documented criteria.
4. Apply configurable business priorities.
5. Explain why each plan ranks where it does.
6. Show costs and risks only when supported by data.
7. State assumptions and unresolved information.

Example explanation:

    Plan A: Reallocate existing spare chairs.
    Benefits: Protects both events and avoids a new purchase.
    Limitation: Requires confirmation that the spare inventory
    is physically available.

If the spare inventory has not been verified, the plan must be marked as needing confirmation.

AI may turn the structured analysis into a clear explanation. It must not alter the validated facts or status.

Output:
Ranked plans with evidence, trade-offs, assumptions, and validation status.

### Layer 8 — Human Approval

**Purpose:** Keep business owners in control of consequential decisions.

Available actions:
- Approve.
- Edit.
- Reject.
- Request more information.

Process:
1. Display the plan and its validation results.
2. Show the assumptions and expected impact.
3. Verify the user's permission.
4. Record the decision.
5. If the user edits the plan, validate it again.
6. Reject approval if the edited plan violates required constraints.
7. Mark the approved plan as ready for action preparation.

Approval does not automatically make unknown facts true. Required confirmations must still be obtained.

Output:
A decision record and the current plan status.

### Layer 9 — Action Preparation and Audit Logging

**Purpose:** Prepare the next operational steps without requiring real external integrations.

Possible outputs:
- Draft supplier messages.
- Draft customer notifications.
- Follow-up tasks.
- Internal assignments.
- Updated simulated job statuses.

Process:
1. Generate action drafts from the approved plan.
2. Require separate approval before any consequential external action.
3. Record the actor, timestamp, decision, and plan version.
4. Track draft, approved, completed, and failed states.
5. Display the resulting activity history.

For the hackathon MVP, messages can remain simulated drafts. Do not claim a message was sent if no integration actually sent it.

Output:
Prepared actions, updated simulated status, and an auditable decision history.

## 4. How the AI and Rules Work Together

Use a hybrid architecture rather than placing every task inside one AI prompt.

| Task | Preferred method |
|---|---|
| Parse an unstructured supplier message | AI with schema validation |
| Validate dates and quantities | Deterministic code |
| Find affected dependencies | Graph traversal and business rules |
| Determine resource availability | Database queries and constraints |
| Generate candidate alternatives | Rules first; AI may suggest more |
| Check plan feasibility | Deterministic validator |
| Rank plans | Documented scoring rules |
| Explain impacts in plain language | AI using validated results |
| Approve an action | Authorized human |
| Record decisions | Backend and database |

The AI adapter should be replaceable. The system should still be able to demonstrate the main workflow if the AI service is unavailable.

## 5. Five-Person Team Division

### Person 1 — Frontend and User Experience

**Main responsibility:** Build the screens and user interactions.

Tasks:
1. Create the business dashboard.
2. Create the disruption submission form.
3. Display the impact analysis.
4. Display recovery-plan comparisons.
5. Build approve, edit, and reject interactions.
6. Display the activity log.
7. Add loading, error, and empty states.
8. Integrate with the backend API.

Deliverables:
- Working frontend.
- API integration.
- Reusable UI components.
- Demo-ready screens.

Dependencies:
- Agreed API request and response schemas.
- Mock JSON data while the backend is being developed.

### Person 2 — Backend, Database, and API

**Main responsibility:** Build the system foundation and shared data contracts.

Tasks:
1. Define database models.
2. Create synthetic seed data.
3. Implement business-data endpoints.
4. Implement disruption endpoints.
5. Implement analysis and recovery orchestration.
6. Connect the algorithm modules.
7. Implement approval endpoints and permission checks.
8. Persist activity logs.
9. Provide a consistent error-response format.

Deliverables:
- Backend service.
- Database schema and seed script.
- API documentation.
- Working endpoints for the frontend and algorithm modules.

Dependencies:
- Agreed entity models and algorithm interfaces.

### Person 3 — Dependency Graph and Impact Analysis

**Main responsibility:** Determine what is affected by a disruption.

Tasks:
1. Define dependency graph structures.
2. Implement graph construction from business records.
3. Implement dependency traversal.
4. Identify direct and downstream impacts.
5. Check resource quantities and dependency conditions.
6. Calculate severity and priority.
7. Explain each impact using evidence.
8. Write unit tests for impact scenarios.

Deliverables:
- Impact-analysis module.
- Structured impact results.
- Test cases and expected outputs.

Dependencies:
- Shared entity definitions.
- A documented input and output contract.

### Person 4 — Recovery Planning and Constraint Validation

**Main responsibility:** Generate candidate plans and verify feasibility.

Tasks:
1. Define the recovery-plan schema.
2. Implement rule-based candidate generation.
3. Add optional AI-generated candidates through a replaceable adapter.
4. Implement resource-allocation checks.
5. Implement deadline and dependency validation.
6. Return feasible, infeasible, or needs-confirmation.
7. Implement plan ranking.
8. Write tests for conflicts and impossible plans.

Deliverables:
- Recovery-plan generator.
- Constraint-validation engine.
- Ranking logic.
- Feasibility tests.

Dependencies:
- Shared entity definitions.
- Impact-analysis output contract.
- Agreed business constraints.

### Person 5 — AI Integration, Explanation, and Evaluation

**Main responsibility:** Add AI-assisted interpretation and explanations, and evaluate the full workflow.

Tasks:
1. Define the AI adapter interface.
2. Implement structured incident extraction from sample messages.
3. Validate extracted fields against the agreed schema.
4. Implement explanation and message-drafting prompts.
5. Ensure AI output uses validated analysis rather than inventing facts.
6. Create AI failure and fallback behavior.
7. Build end-to-end synthetic test scenarios.
8. Measure impact accuracy and plan-validation accuracy.
9. Help prepare the demo and technical documentation.

Deliverables:
- Replaceable AI adapter.
- Structured extraction and explanation modules.
- Evaluation dataset and results.
- Demo scenarios and documentation.

Dependencies:
- Agreed incident and result schemas.
- Stable impact and recovery output formats.

**Important:** Person 5 should not own every AI-related task in isolation. Person 3 and Person 4 own their respective algorithmic logic, and Person 2 owns backend integration. Person 5 focuses on model integration, explanation, and evaluation.

## 6. Shared Contracts Before Parallel Development

The team should agree on shared data structures before implementing the modules.

### Normalized Incident

    {
      "id": "D-001",
      "type": "supplier_delay",
      "supplier_id": "S-01",
      "resource_id": "R-01",
      "quantity_affected": 20,
      "new_arrival_date": "2026-10-22",
      "unresolved_fields": []
    }

### Impact Result

    {
      "disruption_id": "D-001",
      "affected_entities": [
        {
          "entity_type": "job",
          "entity_id": "J-01",
          "impact_status": "confirmed",
          "severity": 8,
          "reason": "Required resource unavailable by deadline",
          "dependency_path": ["S-01", "R-01", "J-01"]
        }
      ],
      "unresolved_facts": []
    }

### Recovery Plan

    {
      "id": "RP-001",
      "disruption_id": "D-001",
      "actions": [],
      "assumptions": [],
      "estimated_cost": null,
      "validation_status": "needs_confirmation",
      "validation_errors": []
    }

### Approval Decision

    {
      "plan_id": "RP-001",
      "reviewer_id": "U-01",
      "decision": "approved",
      "comments": "",
      "plan_version": 1
    }

These are illustrative contracts. The team should refine and version them before coding. In particular, use enums for statuses and validate every payload.

## 7. Parallel Development Strategy

### Phase 1 — Agree on Contracts

Everyone meets to decide:
- Entity names and identifiers.
- Database fields.
- Input and output schemas.
- API endpoints.
- Error formats.
- Status values.
- The exact demo scenario.

Person 2 owns the consolidated contract document, but everyone must review it.

### Phase 2 — Build Independently

While Person 2 builds the backend foundation:
- Person 1 builds the UI using mock JSON responses.
- Person 3 builds impact analysis using fixed test data.
- Person 4 builds plan generation and validation using fixed test data.
- Person 5 builds the AI adapter and evaluation examples.

Each person should commit small, reviewable changes to separate branches.

### Phase 3 — Integrate Modules

1. Connect Person 3's impact engine to the backend.
2. Connect Person 4's recovery planner to the impact results.
3. Connect Person 5's AI adapter to incident extraction and explanation.
4. Connect the frontend to the actual API.
5. Connect approval and audit logging.
6. Run the full synthetic scenario.

### Phase 4 — Test Failure Cases

Test:
- Missing supplier availability.
- Insufficient inventory.
- Conflicting deadlines.
- No feasible recovery plan.
- Invalid AI output.
- AI service unavailable.
- Edited plan becomes infeasible.
- Unauthorized approval.
- Duplicate disruption.
- Database or API error.

### Phase 5 — Prepare the Demo

Freeze the main workflow before the deadline.

Verify:
- One command or documented process starts the application.
- Seed data produces reproducible results.
- The same incident gives predictable impact results.
- Invalid plans are not presented as feasible.
- Approval and activity logging work.
- The GitHub repository contains the demonstrated implementation.

## 8. Testing Strategy

### Unit Tests
- Input validation.
- Entity lookups.
- Graph traversal.
- Impact classification.
- Resource and deadline constraints.
- Plan ranking.
- Permission checks.

### Integration Tests
- Incident submission through impact analysis.
- Impact results through recovery generation.
- Recovery validation through approval.
- Approval through activity logging.

### End-to-End Tests
Run the entire workflow using the event-planning scenario.

### AI Tests
- Valid message extraction.
- Ambiguous dates.
- Unknown supplier names.
- Missing quantities.
- Malformed model output.
- Hallucinated or unsupported entities.
- Model timeout or failure.

For every AI test, verify that invalid or uncertain output is rejected or flagged rather than silently accepted.

## 9. Key Engineering Rules

1. Never let the AI model directly modify database records.
2. Never treat an AI recommendation as proof of feasibility.
3. Validate every proposed plan with deterministic code.
4. Revalidate plans after user edits.
5. Keep unknown facts explicit.
6. Keep model-generated text separate from authoritative structured data.
7. Use mock data and replaceable interfaces to enable parallel development.
8. Avoid adding features that do not support the end-to-end demo.
9. Keep a working fallback if AI is unavailable.
10. Do not claim measured business benefits without test results.

## 10. Definition of Success

The team succeeds when it can demonstrate:

    Supplier Delay
         ↓
    Structured Incident
         ↓
    Dependency-Based Impact Analysis
         ↓
    Candidate Recovery Plans
         ↓
    Deterministic Validation
         ↓
    Explainable Plan Comparison
         ↓
    Human Approval
         ↓
    Prepared Actions and Audit Log

The final result should be a reliable, explainable prototype—not merely a chatbot that suggests what a business owner could do.
