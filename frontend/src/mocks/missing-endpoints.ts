// The single list of endpoints the real backend has NOT built yet.
// In `hybrid` mode MSW answers only these (plus demo-only overlays, see handlers.ts); everything
// else passes through to the backend. Shrink this list as Person 2 ships, and keep
// frontend/INTEGRATION_GAPS.md in step.
//
// Already real (no longer mocked in hybrid): plan edit and revalidate (Person 4), activity-log, request-info, duplicate-report 409,
// and P5's extract, explanation, drafts and draft approve (branch `integration`).
export interface MissingEndpoint {
  method: 'GET' | 'POST' | 'PUT'
  path: string
  reason: string
}

export const MISSING_ENDPOINTS: MissingEndpoint[] = [
  // Nothing is missing any more: Person 4's planner is connected, so PUT /recovery-plans/:id and
  // POST /recovery-plans/:id/revalidate are real in hybrid mode. Their mocks (handlers.ts) now run in `mock` mode only.
  // GET /dashboard is also missing, but the frontend composes it itself (api/endpoints.ts getDashboard).
  // DELETE /recovery-plans/:id/demo-edit is a frontend-only helper for discarding a mock edit (mock mode only).
]
