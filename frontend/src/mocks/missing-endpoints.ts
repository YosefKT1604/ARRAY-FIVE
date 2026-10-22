// The single list of endpoints the real backend has NOT built yet.
// In `hybrid` mode MSW answers only these (plus demo-only overlays, see handlers.ts); everything
// else passes through to the backend. Shrink this list as Person 2 ships, and keep
// frontend/INTEGRATION_GAPS.md in step.
//
// Already real (no longer mocked in hybrid): activity-log, request-info, duplicate-report 409.
export interface MissingEndpoint {
  method: 'GET' | 'POST' | 'PUT'
  path: string
  reason: string
}

export const MISSING_ENDPOINTS: MissingEndpoint[] = [
  { method: 'POST', path: '/disruptions/extract', reason: 'Depends on P5 (AI extraction)' },
  { method: 'GET', path: '/disruptions/:id/explanation', reason: 'Depends on P5 (explanations)' },
  { method: 'PUT', path: '/recovery-plans/:id', reason: 'Plan editing not built (needs P4 validation)' },
  { method: 'POST', path: '/recovery-plans/:id/revalidate', reason: 'Needs P4 validate_plan' },
  { method: 'POST', path: '/recovery-plans/:id/drafts', reason: 'Depends on P5 (drafts)' },
  { method: 'POST', path: '/drafts/:id/approve', reason: 'Depends on P5 (drafts)' },
  // GET /dashboard is also missing, but the frontend composes it itself (api/endpoints.ts getDashboard).
  // DELETE /recovery-plans/:id/demo-edit is a frontend-only helper for discarding a mock edit.
]
