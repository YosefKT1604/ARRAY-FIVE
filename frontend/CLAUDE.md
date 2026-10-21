# CLAUDE.md — Frontend (Person 1)

Put this file in `scdc/frontend/CLAUDE.md`. Claude Code reads it automatically at the start of every session, so these rules survive context resets and new chats.

## Project in one line
SCDC: an AI-assisted disruption-recovery tool for Malaysian small businesses. Core principle: **AI proposes; deterministic logic verifies; humans authorize.**
I own `frontend/` only. Do not edit `backend/`, `docs/`, or `fixtures/` without asking.

## Source of truth (read before coding)
- `../docs/CONTRACTS.md` — types, enums, API endpoints (§7), and error format (§8). **The TypeScript types must mirror it exactly.**
- `../fixtures/demo/*.json` — the demo scenario. Mock responses must be built from these files, not retyped by hand.
- If the contract and these rules disagree, the contract wins. Flag the conflict; don't silently pick one.

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
11. All API calls go through `src/api/client.ts` using the base `/api/v1` and the `X-User-Id` header. Components never call `fetch` directly.
12. Mock vs real is a single switch: `VITE_USE_MOCK=true|false`. With `false`, MSW is off and requests reach the real backend. No component changes.
13. Every data view handles: loading, empty, API error (contract §8 shape), validation error (422 `details[]` mapped to form fields), and uncertain data (`unresolved_*` lists).

## Folder layout
```
frontend/src/
  api/        client.ts, endpoints.ts (one typed function per §7 endpoint)
  types/      contracts.ts (mirror of CONTRACTS.md §3–§8)
  mocks/      handlers.ts, scenarios/ (imports ../../fixtures/demo), browser.ts, server.ts
  components/ StatusBadge, MoneyText, DependencyPath, CheckList, ErrorPanel, EmptyState, UserSwitcher...
  pages/      Dashboard, ReportDisruption, Impact, Plans, PlanReview, Drafts, ActivityLog
  test/       *.test.tsx
```

## Definition of done for any step
`npm run typecheck && npm run lint && npm test && npm run build` all pass. For UI changes, open the page (Playwright MCP or the webapp-testing skill), take a screenshot, and check it before saying the step is done.

## Working style
Small commits on branch `p1-frontend`. After each step, report: what changed, how to test it, and what's still incomplete. Explain things simply: I'm learning (my background is marine biotechnology, not software).
