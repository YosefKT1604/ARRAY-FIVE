# SDC RECOVERY

> When a supplier lets a small business down, see what breaks, compare fixes, and decide in minutes.

---

| Field | Details |
|---|---|
| **Team Name** | ARRAY FIVE |
| **Team Domain** |  Domain 2  |
| **SDG Track (1–17)** | SDG-8: Decent Work and Economic Growth |
| **Team Leader** | Yosef Kristian Tirta |
| **University** | Xiamen University Malaysia |
| **Number of Members** | 5 |

## Links

| Resource | Link |
|---|---|
| GitHub Repository | https://github.com/YosefKT1604/ARRAY-FIVE |
| Live Demo | https://array-five.replit.app |
| Slide Deck | https://canva.link/yxdppt9l7r4bfl2 |
| Demo Video | https://example.com/demo-video |
---

## Overview

### Problem

Small and medium businesses depend on a chain of suppliers, staff and resources to deliver what they've promised their customers. When one link breaks, such as a supplier delivering late or sending fewer items than ordered, one late delivery can put several customer commitments at risk at once.

Large companies handle this with supply-chain software and planning teams. Most small business owners have neither. They hear about disruptions through WhatsApp messages and work out the impact by hand: which jobs need the missing items, whether spare stock exists, which other suppliers can deliver in time, and at what cost. Under time pressure this is easy to get wrong: a supplier that looks cheaper may arrive too late, or a "backup" supplier may not actually have stock.

Generic AI chatbots can suggest ideas, but they can't check whether a plan is actually possible. Businesses need fast recovery options they can trust and stay in control of.

### Reference Scenario

A Kuala Lumpur event planner hears from a supplier, the day before two events, that only 20 of 40 chairs will arrive on time. Both events on that day, a wedding and a corporate seminar, are at risk (2 of 2, 100%), with a 28.6% chair shortfall (50 of 70 chairs available). Neither event can be moved, and the cheapest-looking option (supplier Delima, RM 56) arrives too late.

### Solution

1. **Understand the disruption.** The owner pastes a supplier message (such as an informal WhatsApp text) or fills in a short form. A generative AI model extracts the supplier, item, quantity and new delivery date into a structured format, and rule-based extraction checks them. Any disagreement or uncertain value goes back to the owner to confirm.
2. **Find the impact.** An impact engine follows the business's dependencies (supplier → delivery → resource → job → customer commitment) and calculates which commitments are at risk and how many items are short on each day.
3. **Generate recovery plans.** The system proposes options from real business records: alternative suppliers, spare stock, rescheduling where allowed, or asking the supplier to expedite. AI may suggest extra ideas.
4. **Validate every plan.** A deterministic validator simulates each plan against stock, lead times, deadlines and double-booking, and labels it *feasible*, *infeasible* or *needs confirmation*. AI never decides feasibility, so hallucinated suppliers or stock are never recommended.
5. **Rank and explain.** Feasible plans are ranked by commitments protected, cost and certainty. AI turns the results into clear explanations of the trade-offs.
6. **Human approval.** The owner approves, edits (which triggers revalidation) or rejects a plan. The system then drafts supplier and customer messages (never auto-sent) and records every decision in an activity log.

### Key Features

- **Disruption intake** from a form or a pasted supplier message, with AI and rule-based readings compared
- **Impact analysis** through a dependency graph, showing every affected job and the shortfall per day
- **Checked recovery plans** labelled *feasible*, *infeasible* or *needs confirmation*, then ranked
- **Owner-only approval** with role checks; edited plans are re-validated before they can be approved
- **Draft messages and activity log** for every approved plan and decision
- **Works without AI:** every AI feature has a rule-based or template fallback

## SDG Impact

| Metric | Details |
|---|---|
| **Primary target** | SDG 8.3: support productive activities, entrepreneurship and the growth of micro, small and medium-sized enterprises |
| **Secondary target** | SDG 9.3: increase small enterprises' integration into value chains and markets |
| **Baseline** | MSMEs make up 96.1% of business establishments in Malaysia, contribute 39.5% of GDP and employ 48.7% of the workforce (DOSM, 2024). 55% of Malaysian businesses report their supply chain has been impacted by geopolitical issues (UOB Business Outlook Study 2023). Most micro businesses have no planning tools. |
| **KPI 1 — Commitment protection rate** | % of at-risk customer commitments covered by a validated (feasible) recovery plan |
| **KPI 2 — Time to decide** | Minutes from receiving a supplier message to an approved, validated plan |
| **KPI 3 — Safety rate** | % of plans shown as "feasible" that are actually infeasible (must stay at 0%) |

**Phase 2 targets** (on at least 30 synthetic disruption scenarios, plus a pilot with 3–5 Malaysian micro/small businesses if available):

- ≥ 80% of at-risk commitments protected by a validated plan, wherever a feasible option exists
- ≥ 50% reduction in time to decision compared with solving the scenario by hand
- 0% infeasible plans shown as feasible

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, React Router, TanStack Query, Tailwind CSS 4, Vite 8 |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic 2, SQLAlchemy 2 |
| Database | SQLite (seeded with synthetic demo data) |
| AI | Google Gemini API (Gemini 3.1 Flash-Lite, free tier) through a replaceable LiteLLM adapter, with rule-based fallbacks |
| Hosting | Replit Deployments (one service serves the API and the React frontend); Replit Secrets for the API key |
| Testing | pytest (backend), Vitest, Playwright and Mock Service Worker (frontend) |
| CI / Version control | GitHub and GitHub Actions (tests run on every change) |

## Architecture

```
User (browser)
   │
   ▼
React frontend ──HTTPS / REST──► FastAPI backend (on Replit)
                                    │  validates input, checks permissions
                                    │
                                    ├──► AI module (optional): read supplier message,
                                    │       explain plans, polish drafts
                                    │       (Gemini 3.1 Flash-Lite via LiteLLM, rule-based fallback)
                                    ├──► Impact engine: supplier → delivery → resource → job → commitment
                                    ├──► Recovery planner: generate → validate → rank
                                    ├──► Owner approval → draft supplier and customer messages
                                    └──► SQLite: business data, plans, activity log
```

The AI is called only through an adapter. It never writes to the database or decides feasibility, and the system falls back to rules if the AI is unavailable.

## Project Structure

```
.
├── docs/                    # AI integration, evaluation, contracts and recovery docs
├── fixtures/
│   ├── ai/                  # AI evaluation sets (extraction, explanation, draft cases)
│   └── demo/                # Synthetic demo business data and expected results
├── frontend/                # React + TypeScript app (see frontend/README.md)
├── scripts/
│   ├── build.sh             # Replit build: backend deps + frontend bundle
│   └── start.sh             # Replit run: one server on port 8000
├── src/backend/
│   ├── app/                 # FastAPI app: routers, services, models, schemas, database
│   ├── contracts/           # Shared data contracts between modules
│   ├── impact_engine/       # Dependency graph and impact analysis
│   └── scdc/
│       ├── ai/              # AI extraction, explanations, message drafts, evaluation
│       └── recovery/        # Recovery plan generation, validation, costing and ranking
├── submission/              # Required submission documents
│   ├── SDC2026_ARRAY FIVE_Preliminary.pdf
│   ├── SDC2026_ARRAY FIVE_TechDeclaration.pdf
│   ├── SDC2026_ARRAY FIVE_Replit_POU.pdf
│   └── SDC2026_ARRAY FIVE_Runpod_POU.pdf
├── tests/                   # Backend, impact engine, recovery and AI tests
├── .replit                  # Replit run and deployment configuration
├── LICENSE
├── requirements.txt         # Python dependencies (for setups without uv)
├── SCDC_PLAN.md             # Full algorithm and team implementation plan
└── README.md
```

## How to Run

### Option 1 — Run on Replit (Recommended)

1. Open the Replit project, or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the AI settings listed in `src/backend/.env.example`: `SCDC_AI_PROVIDER`, `SCDC_AI_MODEL`, `SCDC_AI_API_KEY` (and optionally `SCDC_AI_API_BASE`). Without them, every AI feature uses its rule-based fallback.
3. Run `bash scripts/build.sh` once, then click **Run** (`scripts/start.sh` starts the app on port 8000).
4. Click **Publish** to deploy; `.replit` runs the same build and start scripts.

### Option 2 — Run Locally (Windows PowerShell)

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node 20+.

```powershell
# 1. Clone the repository
git clone https://github.com/YosefKT1604/ARRAY-FIVE.git
cd ARRAY-FIVE

# 2. Backend (terminal 1)
cd src\backend
python -m uv sync
$env:SCDC_DEMO_NOW = "2026-10-20T08:00:00+08:00"   # demo date
python -m uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (terminal 2, from the repository root)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The API docs are at http://localhost:8000/docs.

To reset the demo data, from `src\backend`: `python -m uv run python -m app.db.seed`

No uv? From the repository root, once:

```powershell
py -3.12 -m venv src\backend\.venv
.\src\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
cd src\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend modes (`hybrid`, `mock`, `real`) and the demo script are in [frontend/README.md](frontend/README.md).

### Run Tests

```powershell
# Backend, impact engine, recovery and AI (no network or API key needed)
cd src\backend
python -m uv run pytest -q

# Frontend
cd frontend
npm run typecheck; npm run lint; npm test
```

## Testing & Evaluation

- **532 backend tests** and **42 recovery-planning tests**, covering failure cases such as late suppliers, insufficient stock, unknown suppliers, edited plans becoming invalid and AI failure. They run on every change through GitHub Actions.
- **AI evaluation on 62 synthetic cases**: 24 supplier-message extractions, 20 explanations and 18 draft messages, with zero unsafe outputs shown.
- **Demo results** are checked against agreed expected outputs (`fixtures/demo/`: `incident.json`, `expected_impact.json`, `expected_plans.json`).

## How We Use Replit (Required)

Replit is an official SDC sponsor resource.

- **Hosting:** the live prototype runs on Replit Deployments (`.replit` → `scripts/build.sh` and `scripts/start.sh`) at https://array-five.replit.app. One deployment runs the FastAPI backend and serves the React website.
- **Secrets:** the Gemini API key and AI settings are stored in Replit Secrets, never in the code or repository.
- **Not locked in:** the app is standard Python (FastAPI) and React, so it also runs locally or on any other host without changes.

📄 Proof of use: `submission/SDC2026_ARRAY FIVE_Replit_POU.pdf`


## Data, Privacy & Responsible AI

- **No real personal data.** The prototype uses only synthetic demo data for a fictional business (invented supplier, customer and staff names, simulated messages). Login is simulated with demo accounts.
- **What goes to the AI:** only the supplier message text and validated analysis results are sent to Gemini; no contact details, passwords or payment information.
- **Hallucination:** AI output must match a strict schema and is checked against business records; invented suppliers, quantities or dates are rejected.
- **Ambiguous messages** (e.g. "Friday", "kerusi"): AI and rule-based readings are compared, and disagreements are flagged for the owner to confirm.
- **Single provider and rate limits:** the LiteLLM adapter lets another model be swapped in by configuration, and the rule-based fallback keeps the whole workflow running without AI.
- **Unknown facts** (e.g. rental return terms) are marked *needs confirmation*, never *feasible*.
- **Over-trust:** AI text is labelled, AI never edits records, and only the owner role can approve a plan.

## Team & Modules

The system was split into five modules built in parallel against shared data contracts (`docs/CONTRACTS.md`), each on its own branch and merged through pull requests.

| Module | Area | Owner | GitHub |
|---|---|---|---|
| P1 | Frontend: React screens connected to the backend API | Yosef Kristian Tirta | YosefKT1604 |
| P2 | Backend: FastAPI routes, database models, permission checks, activity log | Nicholas Dillon | DillonNicholas |
| P3 | Impact analysis: dependency-graph impact engine | Joshua M. N. Tjoa | Ojojo37 |
| P4 | Recovery planning: plan generator, deterministic validator, ranking | Raymond Russel Willim | raymondwillim|
| P5 | AI module: Gemini adapter, message extraction, explanations, drafts, evaluation sets | Erwin Okto Wu | ErwinOW |

Team members: Yosef Kristian Tirta (Team Leader, [@YosefKT1604](https://github.com/YosefKT1604)), [@DillonNicholas](https://github.com/DillonNicholas), [@ErwinOW](https://github.com/ErwinOW), [@Ojojo37](https://github.com/Ojojo37), [@raymondwillim](https://github.com/raymondwillim).

**Mentoring:** Alpha Red (SDC sponsor) reviewed our system architecture and validation approach.

**AI-assisted development:** Claude Code (Anthropic) was used across all five modules, and OpenAI Codex for learning backend concepts and Python syntax. Each member reviewed the AI-assisted code for their module, and it was verified with the automated tests above.

## Challenges & Learnings

- **Keeping AI honest:** language models can invent stock or dates. We compared a pure-chatbot design with a hybrid one, and chose AI only for reading messages and explaining results, with deterministic rules as the only judge of feasibility.
- **Five people, one system:** agreeing on shared data contracts first let all five members build their modules in parallel with mock data and connect them later.
- **Demo reliability:** every AI feature has a rule-based fallback and the frontend has a mock mode, so the demo works even without a model or network.

## Future Improvements

- [ ] Pilot with 3–5 real Malaysian micro/small businesses to refine the interface and rules
- [ ] Real WhatsApp and supplier integrations (sending approved messages, reading replies)
- [ ] Templates for more industries beyond event planning (catering, retail, workshops)
- [ ] Richer planning model (e.g. rental return terms)
- [ ] Multi-business accounts with real login and PDPA-compliant data handling

## Submission Checklist

- [x] Team name, domain and SDG track filled in
- [x] Slide deck link added
- [ ] Demo video link added
- [x] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [x] Preliminary proposal completed (`SDC2026_ARRAY FIVE_Preliminary.pdf`)
- [x] Technical & Tools Declaration completed (`SDC2026_ARRAY FIVE_TechDeclaration.pdf`)
- [x] Submission files named with the team name
- [ ] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).