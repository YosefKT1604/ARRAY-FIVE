<!-- PRODUCT NAME: decided at team call -->

## Quick start

1. Install Python 3.13, [uv](https://docs.astral.sh/uv/) and Node 20+.
2. Backend, from `srcackend`: `python -m uv sync`
3. Start it: `python -m uv run uvicorn app.main:app --reload --reload-dir app --port 8000`
4. Demo date: `$env:SCDC_DEMO_NOW = "2026-10-20T08:00:00+08:00"` (before step 3).
5. Frontend, from `frontend`: `npm install; npm run dev`, then open http://localhost:5173.
6. Reset the demo data, from `srcackend`: `python -m uv run python -m app.db.seed`
7. Full run steps: [section 18](#18-running-locally). Frontend modes and demo script: [frontend/README.md](frontend/README.md).

# Project README

## 1. Project Overview

**Project Name:** TBD

**Project Type:** AI-assisted business disruption and recovery system

**Target Users:** Malaysian micro and small businesses

### Summary

This project helps small businesses respond to unexpected operational disruptions, such as supplier delays, unavailable equipment, staff absences, and overlapping deadlines.

Instead of requiring business owners to manually check every affected job, the system analyzes business records, identifies downstream impacts, recommends feasible recovery plans, and allows the owner to approve actions before they are carried out.

The system combines deterministic algorithms, structured business data, and AI-assisted interpretation and recommendations.

## 2. Problem Statement

Small businesses often manage their operations through messaging applications, spreadsheets, documents, and manual follow-ups.

When a disruption occurs, owners may need to manually determine:
- Which jobs or customer commitments are affected.
- Which deadlines are at risk.
- Which resources or suppliers can be used as alternatives.
- What actions should be prioritized.
- How to communicate changes to customers and suppliers.

These manual processes can be slow, inconsistent, and difficult to manage when several commitments depend on the same resource or supplier.

## 3. Objectives

1. Identify business commitments affected by a disruption.
2. Trace dependencies between jobs, resources, suppliers, and deadlines.
3. Explain the direct and downstream consequences of an incident.
4. Generate and compare practical recovery options.
5. Validate proposed plans against known business constraints.
6. Require human approval before consequential actions.
7. Maintain an auditable history of decisions and outcomes.
8. Establish an architecture that can later support different industries.

## 4. Target Scenario

The initial MVP will focus on a fictional event-planning business.

Example:

A supplier informs the business that 20 chairs will arrive one day late. The chairs are required for two events scheduled for the following day.

The system should:
1. Record the supplier disruption.
2. Identify both affected events.
3. Check event dates, chair requirements, inventory, and alternative suppliers.
4. Explain which commitments are at risk.
5. Compare feasible recovery options.
6. Let the owner approve, edit, or reject a recommendation.
7. Record the decision and prepare relevant follow-up messages.

The architecture should be reusable for other businesses, but the MVP will prioritize completing this one scenario reliably.

## 5. Main Features

### 5.1 Business Context Management
- Manage jobs, events, commitments, suppliers, and resources.
- Store deadlines, quantities, availability, and dependencies.
- Use synthetic data for the prototype.

### 5.2 Disruption Input
- Allow users to report a disruption through a structured form.
- Support examples such as delayed deliveries and unavailable equipment.
- Optionally extract information from a sample supplier message using AI.

### 5.3 Impact Analysis
- Identify directly affected commitments.
- Trace downstream dependencies.
- Highlight deadlines and resource shortages.
- Distinguish confirmed facts from uncertain information.
- Explain why each item is affected.

### 5.4 Recovery Planning
- Generate alternative recovery options.
- Check resource availability and deadlines.
- Estimate cost and operational trade-offs when data is available.
- Rank feasible options according to business priorities.
- Explain the strengths, weaknesses, and assumptions of each option.

### 5.5 Human Approval
- Allow authorized users to review recommendations.
- Support approve, edit, and reject actions.
- Revalidate plans after edits.
- Prevent unapproved actions from being executed.

### 5.6 Action Tracking
- Prepare draft messages for suppliers or customers.
- Create follow-up tasks.
- Record approvals, rejections, edits, and status changes.
- Show an activity history for the incident.

### 5.7 Dashboard
- Display active disruptions.
- Summarize affected commitments.
- Highlight urgent decisions.
- Show recovery-plan status and outstanding approvals.

## 6. System Design

### High-Level Architecture

    User Interface
         |
         v
    Backend API
         |
         v
    Disruption Processing Service
         |
         v
    Business Context Retrieval
         |
         v
    Impact Analysis Engine
         |
         v
    Recovery Planning Engine
         |
         v
    Constraint Validation Engine
         |
         v
    Recommendation and Explanation Layer
         |
         v
    Human Approval
         |
         v
    Action Preparation and Activity Log

    Supporting Components:
    - Relational Database
    - Optional AI Model/API
    - Authentication and Role Checks
    - Test Data and Evaluation Suite

### Core Design Principle

**AI proposes; deterministic logic verifies; humans authorize.**

AI may interpret messages, summarize incidents, and help generate recovery ideas. It must not be the sole authority for determining resource availability, dependency relationships, deadline feasibility, or permission to execute an action.

## 7. AI and Algorithm Strategy

### Deterministic Components
- Data validation and normalization.
- Dependency graph traversal.
- Deadline and resource checks.
- Impact severity calculations.
- Recovery-plan feasibility validation.
- Approval and permission enforcement.
- Activity logging.

### AI-Assisted Components
- Extracting structured incident information from text.
- Summarizing affected commitments.
- Generating explanations in plain language.
- Suggesting candidate recovery actions.
- Drafting supplier and customer messages.

### AI Safety Rules
- Validate extracted information against stored business records.
- Mark missing or ambiguous information as unknown.
- Never invent supplier availability, costs, or deadlines.
- Reject or flag plans that fail deterministic validation.
- Require human approval before consequential actions.
- Keep AI-generated messages as drafts until approved.

## 8. Suggested Technology Stack

The team should agree on one stack before implementation.

A practical option:

- **Frontend:** React with TypeScript.
- **Backend:** Python with FastAPI.
- **Database:** PostgreSQL, or SQLite for a simpler local prototype.
- **Data Validation:** Pydantic.
- **Dependency Analysis:** Python graph structures or NetworkX.
- **AI Integration:** A replaceable model/API adapter.
- **Testing:** Pytest for backend logic; frontend component and workflow tests.
- **Version Control:** Git and GitHub.
- **Deployment:** One hosted frontend and backend, or a single demonstrable local environment.

Avoid adding complex infrastructure unless it directly supports the MVP.

## 9. Database Structure

Suggested entities:

### BusinessJob
- id
- name
- description
- deadline
- status
- priority

### Supplier
- id
- name
- contact_reference
- reliability_notes

### Resource
- id
- name
- total_quantity
- available_quantity
- availability_period

### Commitment
- id
- job_id
- commitment_type
- required_date
- status

### Dependency
- id
- source_type
- source_id
- target_type
- target_id
- dependency_type
- required_quantity

### Disruption
- id
- type
- description
- affected_entity
- reported_at
- severity
- status

### RecoveryPlan
- id
- disruption_id
- plan_summary
- feasibility_status
- estimated_cost
- assumptions
- status

### RecoveryAction
- id
- recovery_plan_id
- action_type
- target_entity
- parameters
- validation_status

### Approval
- id
- recovery_plan_id
- reviewer_id
- decision
- comments
- decided_at

### ActivityLog
- id
- disruption_id
- actor_id
- action_type
- details
- created_at

Use foreign keys where appropriate. Store quantities, costs, and timestamps using appropriate data types. Exact fields can be adjusted during implementation.

## 10. API Structure

Suggested endpoints:

### Business Data
- GET /jobs
- POST /jobs
- GET /suppliers
- GET /resources
- GET /dependencies

### Disruptions
- POST /disruptions
- GET /disruptions
- GET /disruptions/{id}

### Analysis and Recovery
- POST /disruptions/{id}/analyze
- GET /disruptions/{id}/impact
- POST /disruptions/{id}/recovery-plans
- GET /recovery-plans/{id}

### Approval and Actions
- POST /recovery-plans/{id}/approve
- POST /recovery-plans/{id}/reject
- POST /recovery-plans/{id}/revalidate
- GET /disruptions/{id}/activity-log

These are proposed contracts, not existing endpoints. The team must define request and response schemas before parallel development.

## 11. Core Workflow

1. User reports a disruption.
2. System validates the input.
3. System extracts structured facts if AI is needed.
4. System retrieves relevant business records.
5. Impact engine identifies affected commitments.
6. Recovery engine generates candidate plans.
7. Validation engine checks every plan.
8. System ranks feasible plans and explains trade-offs.
9. Owner reviews and approves, edits, or rejects a plan.
10. Edited plans are revalidated.
11. System prepares follow-up actions.
12. System records the decision and displays the updated status.

## 12. MVP Scope

### Must Have
- Synthetic business data.
- One disruption scenario.
- Dependency-based impact analysis.
- At least two recovery options where the data permits.
- Deterministic feasibility checks.
- Human approval flow.
- Activity log.
- Working end-to-end interface.
- Reproducible demo and accessible GitHub repository.

### Not Required for the MVP
- Real supplier integrations.
- Sending real WhatsApp messages.
- Real payments.
- Autonomous contractual changes.
- Full ERP, POS, or project-management functionality.
- Learning a custom machine-learning model from historical incidents.
- Support for every industry from day one.

## 13. Evaluation and Testing

Test the system with scenarios including:

1. A disruption affecting one job.
2. A shared resource affecting multiple jobs.
3. An available alternative supplier.
4. No feasible recovery plan.
5. Missing supplier availability information.
6. Conflicting deadlines or quantities.
7. A user editing a proposed plan into an infeasible plan.
8. An unauthorized user attempting approval.
9. An AI extraction error.
10. A repeated incident submission.

Measure:
- Impact identification accuracy.
- Feasibility-validation accuracy.
- Time needed to understand a disruption.
- Time needed to reach a decision.
- Percentage of recommendations with clear explanations.
- Whether invalid or uncertain plans are correctly flagged.

Use predefined synthetic test cases and report measured results honestly.

## 14. Privacy and Responsible Use

- Use synthetic data in the hackathon prototype.
- Avoid exposing customer or supplier information to AI services unnecessarily.
- Restrict actions according to user permissions.
- Keep an audit trail of important decisions.
- Apply appropriate data minimization, access control, retention, and consent practices in a real deployment.
- Review applicable Malaysian PDPA obligations before handling real personal data.

## 15. Business Value and Challenge Fit

The system aims to reduce manual coordination and help SMEs make more informed decisions when operations are disrupted.

Its value comes from tracing downstream impacts, comparing feasible recovery plans, and keeping decisions under human control.

The prototype should demonstrate:
- A clear recurring business problem.
- A complete operational workflow.
- Practical, explainable automation.
- Human approval and auditability.
- Potential reuse across different SMEs.
- A realistic implementation and growth path.

The primary SDG alignment is **SDG 8: Decent Work and Economic Growth**, through improved operational productivity and support for small businesses.

## 16. Demo Plan

1. Open the fictional business dashboard.
2. Show several scheduled events and shared resources.
3. Enter a supplier-delay incident.
4. Display all affected commitments and explain the dependency chain.
5. Compare feasible recovery options.
6. Demonstrate an infeasible option being rejected.
7. Approve one valid plan.
8. Show prepared follow-up messages and tasks.
9. Open the activity log to inspect the decision history.

## 17. Definition of Done

The MVP is ready when:
- The full workflow can be demonstrated from start to finish.
- Impact analysis matches the expected results of predefined test cases.
- Recovery plans are validated against known constraints.
- Missing or conflicting information is surfaced.
- Approval and rejection work correctly.
- Important decisions are recorded.
- The demo can be reproduced from documented setup instructions.
- The repository matches the demonstrated functionality.

## 18. Running Locally

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

Run these from `src/backend`:

```bash
uv sync
uv run python -m app.db.seed
uv run uvicorn app.main:app --reload --port 8000
```

The API is then at `http://localhost:8000/api/v1`, and the interactive docs are at http://localhost:8000/docs`.

The server creates and seeds the database on first start. Running the seed command again resets it to the demo data.

### Backend without uv (Windows PowerShell)

From the repository root, once:

```powershell
py -3.13 -m venv src\backend\.venv
.\src\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```

Then start the server from `src\backend`:

```powershell
cd src\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### Demo date and AI settings

The demo story happens on Tuesday 20 Oct 2026. To make the backend agree with the frontend's demo date (how
"tomorrow" and "Friday" in a message are read, and the date impact scores are measured from), set this before
starting the server, or put it in `src/backend/.env` (copy `src/backend/.env.example`):

```powershell
$env:SCDC_DEMO_NOW = "2026-10-20T08:00:00+08:00"
```

Without an AI model (the default) every AI feature uses its rule-based or template fallback. To connect a model,
see `docs/AI_INTEGRATION.md` section 6.

### Frontend

Requires Node 20+. In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The default `hybrid` mode uses the real backend and mocks only what is not built yet;
`mock` mode needs no backend. See `frontend/README.md` for the modes and the demo script.

### Tests

From the repository root:

```powershell
.\src\backend\.venv\Scripts\python.exe -m pytest -q    # backend, impact engine and AI module; no network, no key
```

From `frontend`: `npm run typecheck; npm run lint; npm test; npm run build`.