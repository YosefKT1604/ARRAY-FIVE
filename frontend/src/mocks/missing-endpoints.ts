// The single list of endpoints the real backend has NOT built yet.
// In `hybrid` mode MSW answers only these; everything else passes through to the backend.
// Shrink this list as Person 2 ships (and keep frontend/INTEGRATION_GAPS.md in step).
export interface MissingEndpoint {
  method: 'GET' | 'POST' | 'PUT'
  path: string
  reason: string
  /** Milestone that adds the mock handler. */
  milestone: string
}

export const MISSING_ENDPOINTS: MissingEndpoint[] = [
  { method: 'POST', path: '/disruptions/extract', reason: 'Depends on P5 (AI extraction)', milestone: 'M2' },
  { method: 'GET', path: '/disruptions/:id/explanation', reason: 'Depends on P5 (explanations)', milestone: 'M3' },
  { method: 'PUT', path: '/recovery-plans/:id', reason: 'Plan editing not built', milestone: 'M3' },
  { method: 'POST', path: '/recovery-plans/:id/revalidate', reason: 'Needs P4 validate_plan', milestone: 'M3' },
  { method: 'POST', path: '/recovery-plans/:id/request-info', reason: 'Not built', milestone: 'M3' },
  { method: 'POST', path: '/recovery-plans/:id/drafts', reason: 'Depends on P5 (drafts)', milestone: 'M4' },
  { method: 'POST', path: '/drafts/:id/approve', reason: 'Depends on P5 (drafts)', milestone: 'M4' },
  { method: 'GET', path: '/disruptions/:id/activity-log', reason: 'No ActivityLog table yet', milestone: 'M4' },
  // GET /dashboard is also missing, but the frontend composes it itself (api/endpoints.ts getDashboard),
  // so no mock is needed.
]
