import { http, HttpResponse, type RequestHandler } from 'msw'
import { API_BASE } from '../config'
import type { DecisionRequest } from '../types/contracts'
import {
  analyzeMockDisruption,
  createMockDisruption,
  fixtures,
  generateMockPlans,
  nextApprovalId,
  state,
  userRole,
} from './db'

const url = (path: string) => `${API_BASE}${path}`

/** Same error shape as the real backend (RFC 9457 Problem Details). */
function problem(status: number, detail: string, instance: string) {
  const title = { 401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 409: 'Conflict' }[status] ?? 'Error'
  return HttpResponse.json(
    { type: 'about:blank', title, status, detail, instance },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  )
}

/**
 * Mocks of endpoints the real backend HAS built. Registered only in `mock` mode, so the whole
 * demo runs offline. Behaviour mirrors the backend stubs (see INTEGRATION_GAPS.md).
 */
export const mockedBackendHandlers: RequestHandler[] = [
  http.get(url('/health'), () => HttpResponse.json({ status: 'ok' })),
  http.get(url('/jobs'), () => HttpResponse.json({ items: fixtures.seed.jobs })),
  http.get(url('/resources'), () => HttpResponse.json({ items: fixtures.seed.resources })),
  http.get(url('/deliveries'), () => HttpResponse.json({ items: fixtures.seed.deliveries })),
  http.get(url('/dependencies'), () => HttpResponse.json({ items: fixtures.seed.dependencies })),
  http.get(url('/suppliers'), () =>
    HttpResponse.json({
      items: fixtures.seed.suppliers.map((s) => ({
        ...s,
        offerings: fixtures.seed.supplier_offerings.filter((o) => o.supplier_id === s.id),
      })),
    }),
  ),

  http.get(url('/disruptions'), () => HttpResponse.json({ items: state.disruptions })),
  http.post(url('/disruptions'), async ({ request }) => {
    const body = (await request.json()) as Parameters<typeof createMockDisruption>[0]
    const { disruption, incident } = createMockDisruption(body)
    return HttpResponse.json({ disruption, incident, validation_errors: [] }, { status: 201 })
  }),
  http.get(url('/disruptions/:id'), ({ params }) => {
    const d = state.disruptions.find((x) => x.id === params.id)
    return d ? HttpResponse.json(d) : problem(404, `Disruption ${params.id} not found`, `/disruptions/${params.id}`)
  }),
  http.post(url('/disruptions/:id/analyze'), ({ params }) => {
    const d = state.disruptions.find((x) => x.id === params.id)
    if (!d) return problem(404, `Disruption ${params.id} not found`, `/disruptions/${params.id}/analyze`)
    if (d.status === 'needs_clarification')
      return problem(409, 'Disruption needs clarification before it can be analyzed', `/disruptions/${d.id}/analyze`)
    return HttpResponse.json(analyzeMockDisruption(d))
  }),
  http.get(url('/disruptions/:id/impact'), ({ params }) => {
    const impact = state.impacts[params.id as string]
    return impact
      ? HttpResponse.json(impact)
      : problem(404, `Disruption ${params.id} has not been analyzed yet`, `/disruptions/${params.id}/impact`)
  }),
  http.post(url('/disruptions/:id/recovery-plans'), ({ params }) => {
    const d = state.disruptions.find((x) => x.id === params.id)
    if (!d) return problem(404, `Disruption ${params.id} not found`, `/disruptions/${params.id}/recovery-plans`)
    if (d.status !== 'analyzed')
      return problem(409, `Plans need an analyzed disruption; ${d.id} is ${d.status}`, `/disruptions/${d.id}/recovery-plans`)
    return HttpResponse.json({ items: generateMockPlans(d) }, { status: 201 })
  }),
  http.get(url('/disruptions/:id/recovery-plans'), ({ params }) =>
    HttpResponse.json({ items: state.plans.filter((p) => p.disruption_id === params.id) }),
  ),
  http.get(url('/recovery-plans/:id'), ({ params }) => {
    const p = state.plans.find((x) => x.id === params.id)
    return p ? HttpResponse.json(p) : problem(404, `Recovery plan ${params.id} not found`, `/recovery-plans/${params.id}`)
  }),
  http.post(url('/recovery-plans/:id/approve'), (ctx) => decide(ctx, 'approved')),
  http.post(url('/recovery-plans/:id/reject'), (ctx) => decide(ctx, 'rejected')),
]

async function decide(
  { params, request }: { params: Record<string, unknown>; request: Request },
  decision: 'approved' | 'rejected',
) {
  const verb = decision === 'approved' ? 'approve' : 'reject'
  const instance = `/recovery-plans/${params.id}/${verb}`
  const userId = request.headers.get('X-User-Id')
  const role = userRole(userId)
  if (!role) return problem(401, 'Missing or unknown X-user-id header', instance)
  const plan = state.plans.find((x) => x.id === params.id)
  if (!plan) return problem(404, `Recovery plan ${params.id} not found`, instance)
  if (role !== 'owner') return problem(403, `${userId} (${role}) may not approve or reject plans`, instance)
  const body = (await request.json()) as DecisionRequest
  if (body.plan_version !== plan.version)
    return problem(409, `Plan ${plan.id} is at version ${plan.version}, not ${body.plan_version}`, instance)
  if (plan.status !== 'proposed') return problem(409, `Plan ${plan.id} is already ${plan.status}`, instance)
  if (decision === 'approved' && plan.validation?.status === 'infeasible')
    return problem(409, `Plan ${plan.id} is infeasible and cannot be approved`, instance)

  plan.status = decision === 'approved' ? 'approved' : 'rejected'
  if (decision === 'approved') {
    const d = state.disruptions.find((x) => x.id === plan.disruption_id)
    if (d) d.status = 'decided'
  }
  const approval = {
    id: nextApprovalId(),
    plan_id: plan.id,
    plan_version: plan.version,
    reviewer_id: userId!,
    decision,
    comments: body.comments ?? '',
    decided_at: new Date().toISOString(),
  }
  state.approvals.push(approval)
  return HttpResponse.json(approval, { status: 201 })
}

/**
 * Mocks of endpoints the backend has NOT built (list: missing-endpoints.ts). Always registered
 * in `mock` and `hybrid` modes. Handlers are added milestone by milestone.
 */
export const missingEndpointHandlers: RequestHandler[] = []
