# CLAUDE.md: ARRAY-FIVE (preliminary submission phase)

Claude Code reads this file at the start of every session in this repo.

## The project
An AI-assisted disruption-recovery tool for Malaysian micro and small businesses: SDC Hackathon, **Domain 2 "Orbyte Smart SME Challenge"** (sponsor: Alpha Red Solutions).
The journey judges must see live: **trigger** (a supplier's WhatsApp message) → **connected data** → **decision logic** → **human approval** → **visible outcome + activity log**.
Core principle: **AI proposes, rules verify, humans decide.**
Preliminary deadline: **Sun 25 Oct 2026, 07:59:59 MYT.** Feature freeze: **Sat 24 Oct, 20:00 MYT.**

## Layout
- `src/backend/`: FastAPI app (`app/`, Person 2), contracts (`contracts/`), impact engine (`impact_engine/`, Person 3), AI module (`scdc/ai/`, Person 5)
- `src/backend/app/services/recovery.py`: recovery planning. **Still a placeholder until Person 4's module arrives**
- `frontend/`: React + TypeScript + Vite (Person 1). It has its own `frontend/CLAUDE.md` for UI rules
- `fixtures/demo/`: the demo business and its expected results. `fixtures/ai/`: AI evaluation cases
- `docs/`: `CONTRACTS.md` (shared contract), `AI_INTEGRATION.md`, `AI_EVALUATION.md`

## Commands (Windows PowerShell; the user is on Windows)
- Backend setup, from `src\backend`: `python -m uv sync`
- Backend run, from `src\backend`: `python -m uv run uvicorn app.main:app --reload --reload-dir app --port 8000`
- Reset the demo data, from `src\backend`: `python -m uv run python -m app.db.seed`
- Backend tests, from the repo root: `src\backend\.venv\Scripts\python.exe -m pytest -q`
- Frontend, from `frontend`: `npm run typecheck; npm run lint; npm test; npm run build; npm run test:e2e`
- Demo date: `$env:SCDC_DEMO_NOW = "2026-10-20T08:00:00+08:00"`

## Rules
1. **Never break the demo.** A task is done only when all backend tests, all frontend checks and the e2e test pass.
2. **Never show a plan as working unless deterministic validation produced that status for THIS incident.** No fixture or placeholder output may be shown as checked.
3. **Change only what the task asks.** Other owners' modules (`impact_engine/`, `scdc/ai/`, the recovery module) are used through their public functions. If a task needs a change inside one, keep it minimal and say so in the commit message.
4. **No secrets in the repo** (handbook 6.1.6): no API keys, tokens or passwords in code, docs, tests or commit messages. Keys live in Replit Secrets or a git-ignored `.env`.
5. **Git:** work on the current feature branch with small, clear commits, and push after each task. Never force-push, never rewrite `main`, never delete branches.
6. **Stop every server or background process you start** before you finish.
7. **Keep `docs/CONTRACTS.md` compatible.** Errors use the Problem format with a `code` field.
8. **Write UI text for a busy business owner:** plain words, no IDs or codes on screen (they go in "Details").
9. **After each task, report in 5 lines:** what changed, how to try it, the test results, what's incomplete, and anything the team must decide.
