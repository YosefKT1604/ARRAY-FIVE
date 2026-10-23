# CLAUDE.md — Frontend (Person 1)

Claude Code reads this file automatically at the start of every session in `frontend/`. The root `CLAUDE.md` also applies.

## Project in one line
SCDC: an AI-assisted disruption-recovery tool for Malaysian small businesses. Core principle: **AI proposes; deterministic logic verifies; humans authorize.**
I own `frontend/` only. Do not edit `src/backend/`, `docs/`, or `fixtures/` without asking.

## Source of truth (read before coding)
- **The real backend (Person 2)** in this repo at `../src/backend`, run locally at `http://localhost:8000` (from `srcackend`: `python -m uv run uvicorn app.main:app --reload --reload-dir app --port 8000`). Its OpenAPI schema (`http://localhost:8000/openapi.json`) is what the frontend actually talks to. **Generate TS types from it** with `openapi-typescript` into `src/types/api.generated.ts`. Never hand-edit that file; regenerate it with `npm run gen:api`.
- `../docs/CONTRACTS.md` — the agreed intent: enums, error format (§8), the demo scenario (§9), and endpoints P2 hasn't built yet.
- `../fixtures/demo/*.json` — the demo scenario. Mock responses must be built from these files, not retyped by hand.
- If the backend and CONTRACTS.md disagree, **don't silently pick one**. Record it in `frontend/INTEGRATION_GAPS.md` (endpoint, contract says, backend does, impact on UI) and ask me. Default: follow the real backend for what exists, and the contract for what's missing.
- **Never edit backend code.** It belongs to Person 2. Report problems in INTEGRATION_GAPS.md instead.

## Stack (fixed)
Vite + React + TypeScript (strict) · React Router · TanStack Query · Tailwind CSS + shadcn/ui · MSW (Mock Service Worker) for the mock API · Vitest + React Testing Library · Playwright for one end-to-end demo test.

## Hard rules
1. **Keep JSON keys in snake_case** in the TS types, exactly as in the contract. Don't add a camelCase mapping layer.
2. **The frontend never computes `validation.status`, `impact_status`, `rank` or severity.** It only displays what the API returns. (P4 owns validation; P3 owns impact.)
3. Status display:
   - `feasible` → green, "Checked: works with known data"
   - `needs_confirmation` → amber, "Needs confirmation", and list `unresolved_assumptions`
   - `infeasible` → red, "Won't work", and list the failing checks in plain language
   - Never show an unvalidated or `needs_confirmation` plan as definitely feasible.
4. `infeasible` plans: the Approve button is disabled, with the reason shown.
5. Editing a plan creates a new version (`PUT /recovery-plans/{id}` with `base_version`). Show the new validation result. Never reuse the old status.
6. Money is `{"amount": "80.00", "currency": "MYR"}` → display "RM 80.00". `null` → "Cost unknown". **Never show RM 0.00 for unknown.**
7. Dates and timestamps are displayed in `Asia/Kuala_Lumpur`.
8. Any text with `generated_by` starting with `model:` gets an "AI-generated" badge.
9. Draft messages always say "Draft — not sent". Nothing in this app sends anything.
10. In mock mode, show a visible "Demo data (mock)" banner. Never claim an action was persisted to a server.
11. All API calls go through `src/api/client.ts` using the backend's real base path (expected `/api/v1`; confirm from openapi.json) and the `X-User-Id` header. Components never call `fetch` directly.
12. In development, the **Vite dev server proxies `/api` to `http://localhost:8000`**, so the browser sees one origin and CORS isn't needed.
13. API mode is one setting, `VITE_API_MODE`:
    - `mock`: MSW answers everything (offline demo, and the backup if the backend breaks during judging).
    - `hybrid` (the default during development): MSW answers **only** endpoints the backend hasn't built yet; everything else passes through to the real backend (`onUnhandledRequest: 'bypass'`). Keep the list of mocked endpoints in one file, `src/mocks/missing-endpoints.ts`, and shrink it as P2 ships.
    - `real`: MSW is off.
    The UI shows a small badge with the current mode.
14. Every data view handles: loading, empty, API error (contract §8 shape), validation error (422 `details[]` mapped to form fields), and uncertain data (`unresolved_*` lists).

## Folder layout
```
frontend/src/
  api/        client.ts, endpoints.ts (one typed function per §7 endpoint)
  types/      api.generated.ts (from openapi.json, never hand-edited), contracts.ts (friendly aliases + enums + types for endpoints not built yet)
  mocks/      handlers.ts, scenarios/ (imports ../../fixtures/demo), browser.ts, server.ts
  components/ StatusBadge, MoneyText, DependencyPath, CheckList, ErrorPanel, EmptyState, UserSwitcher...
  pages/      Dashboard, ReportDisruption, Impact, Plans, PlanReview, Drafts, ActivityLog
  test/       *.test.tsx
```

## Definition of done for any step
`npm run typecheck; npm run lint; npm test; npm run build` all pass (Windows PowerShell has no `&&`), and `npm run test:e2e` passes. If the backend is running, also click through the changed screen in `hybrid` mode against it. For UI changes, open the page (Playwright MCP or the webapp-testing skill), take a screenshot, and check it before saying the step is done.

## Working style
Small commits on the current feature branch. After each step, report: what changed, how to test it, and what's still incomplete. Explain things simply: I'm learning (my background is marine biotechnology, not software).
