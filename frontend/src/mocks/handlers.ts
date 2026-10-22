import { bypass, http, HttpResponse, passthrough, type RequestHandler } from 'msw'
import { API_BASE, API_MODE } from '../config'
import type { Approval, DecisionRequest, Disruption, PlanEditRequest, RecoveryPlan } from '../types/contracts'
import {
  analyzeMockDisruption,
  createMockDisruption,
  fixtures,
  generateMockPlans,
  nextApprovalId,
  state,
  userRole,
} from './db'
import { mockEdit } from './edit'
import { buildExplanation } from './explanation'
import { mockExtract } from './extract'

const url = (path: string) => `${API_BASE}${path}`

/** Same error shape as the real backend (RFC 9457 Problem Details). */
function problem(status: number, detail: string, instance: string) {
  const title = { 401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 409: 'Conflict', 422: 'Unprocessable Entity' }[status] ?? 'Error'
  return HttpResponse.json(
    { type: 'about:blank', title, status, detail, instance },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  )
}

/** Latest demo version of a plan, if the mock has edited or decided it. */
const overlay = (plan: RecoveryPlan): RecoveryPlan => state.demoPlans[plan.id] ?? plan

/** Read from the REAL backend from inside a handler (hybrid mode). */
async function fetchReal<T>(path: string, origin: string): Promise<T | null> {
  const res = await fetch(bypass(new Request(`${origin}${API_BASE}${path}`)))
  return res.ok ? ((await res.json()) as T) : null
}

/** Find a plan wherever it lives: demo overlay, mock state, or (hybrid) the real backend. */
async function resolvePlan(id: string, request: Request): Promise<RecoveryPlan | null> {
  if (state.demoPlans[id]) return state.demoPlans[id]
  if (API_MODE === 'mock') return state.plans.find((p) => p.id === id) ?? null
  return fetchReal<RecoveryPlan>(`/recovery-plans/${id}`, new URL(request.url).origin)
}

async function resolvePlans(disruptionId: string, request: Request): Promise<RecoveryPlan[]> {
  if (API_MODE === 'mock') return state.plans.filter((p) => p.disruption_id === disruptionId).map(overlay)
  const real = await fetchReal<{ items: RecoveryPlan[] }>(`/disruptions/${disruptionId}/recovery-plans`, new URL(request.url).origin)
  return (real?.items ?? []).map(overlay)
}

/** Mock-only business rules: the material fields of CONTRACTS.md section 6.1 must be present. */
function validateDisruptionBody(body: Parameters<typeof createMockDisruption>[0]) {
  const bad = (field: string, msg: string) => ({ loc: ['body', field], msg, type: 'value_error' })
  const problems = []
  if (!body.supplier_id) problems.push(bad('supplier_id', 'Choose the supplier'))
  if (!body.resource_id) problems.push(bad('resource_id', 'Choose what is affected'))
  if (body.quantity_affected == null || body.quantity_affected < 1) problems.push(bad('quantity_affected', 'Must be at least 1'))
  if (!body.new_arrival_date) problems.push(bad('new_arrival_date', 'Enter the new arrival date'))
  return problems
}

type Ctx = { params: Record<string, unknown>; request: Request }
type Decision = 'approved' | 'rejected' | 'more_info_requested'

/**
 * Approve / reject / request-info on a plan the MOCK owns. Mirrors the backend's rules
 * (403 non-owner, 409 stale version, 409 already decided, 409 infeasible).
 */
async function decide({ request }: Ctx, plan: RecoveryPlan, decision: Decision, verb: string) {
  const instance = `/recovery-plans/${plan.id}/${verb}`
  const userId = request.headers.get('X-User-Id')
  const role = userRole(userId)
  if (!role) return problem(401, 'Missing or unknown X-user-id header', instance)
  if (role !== 'owner') return problem(403, `${userId} (${role}) may not approve or reject plans`, instance)
  const body = (await request.json()) as DecisionRequest
  if (decision !== 'approved' && !body.comments?.trim()) {
    return HttpResponse.json(
      {
        type: 'about:blank',
        title: 'Unprocessable Entity',
        status: 422,
        detail: 'Validation failed',
        instance,
        errors: [{ loc: ['body', 'comments'], msg: 'A comment is required', type: 'value_error' }],
      },
      { status: 422, headers: { 'Content-Type': 'application/problem+json' } },
    )
  }
  if (body.plan_version !== plan.version)
    return problem(409, `Plan ${plan.id} is at version ${plan.version}, not ${body.plan_version}`, instance)
  if (plan.status !== 'proposed') return problem(409, `Plan ${plan.id} is already ${plan.status}`, instance)
  if (decision === 'approved' && plan.validation?.status === 'infeasible')
    return problem(409, `Plan ${plan.id} is infeasible and cannot be approved`, instance)

  state.demoPlans[plan.id] = {
    ...plan,
    status: decision === 'approved' ? 'approved' : decision === 'rejected' ? 'rejected' : 'more_info_requested',
  }
  if (decision === 'approved') {
    state.demoDecided.push(plan.disruption_id)
    const d = state.disruptions.find((x) => x.id === plan.disruption_id)
    if (d) d.status = 'decided'
  }
  const approval: Approval = {
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
    const fieldProblems = validateDisruptionBody(body)
    if (fieldProblems.length)
      return HttpResponse.json(
        { type: 'about:blank', title: 'Unprocessable Entity', status: 422, detail: 'Validation failed', instance: '/disruptions', errors: fieldProblems },
        { status: 422, headers: { 'Content-Type': 'application/problem+json' } },
      )
    // Mock-only (the real backend has no duplicate check yet): answers in the contract section 8 shape.
    const existing = state.disruptions.find(
      (d) =>
        d.status !== 'closed' &&
        d.incident.delivery_id === (body.delivery_id ?? null) &&
        d.incident.new_arrival_date === (body.new_arrival_date ?? null),
    )
    if (existing)
      return HttpResponse.json(
        {
          error: {
            code: 'DUPLICATE_DISRUPTION',
            message: `This delay is already reported as ${existing.id}.`,
            details: [{ field: 'existing_id', issue: existing.id }],
            request_id: 'mock-dup',
          },
        },
        { status: 409 },
      )
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
    HttpResponse.json({ items: state.plans.filter((p) => p.disruption_id === params.id).map(overlay) }),
  ),
  http.get(url('/recovery-plans/:id'), ({ params }) => {
    const p = state.plans.find((x) => x.id === params.id)
    return p ? HttpResponse.json(overlay(p)) : problem(404, `Recovery plan ${params.id} not found`, `/recovery-plans/${params.id}`)
  }),
  http.post(url('/recovery-plans/:id/approve'), (ctx) => decideBuiltIn(ctx, 'approved', 'approve')),
  http.post(url('/recovery-plans/:id/reject'), (ctx) => decideBuiltIn(ctx, 'rejected', 'reject')),
]

async function decideBuiltIn(ctx: Ctx, decision: Decision, verb: string) {
  const p = state.plans.find((x) => x.id === ctx.params.id)
  if (!p) return problem(404, `Recovery plan ${ctx.params.id} not found`, `/recovery-plans/${ctx.params.id}/${verb}`)
  return decide(ctx, overlay(p), decision, verb)
}

/**
 * Mocks of endpoints the backend has NOT built (list: missing-endpoints.ts). Always registered
 * in `mock` and `hybrid` modes. Everything here is labelled "Demo only" in the UI.
 */
export const missingEndpointHandlers: RequestHandler[] = [
  http.post(url('/disruptions/extract'), async ({ request }) => {
    const { message, from_contact } = (await request.json()) as { message: string; from_contact?: string | null }
    return HttpResponse.json(mockExtract(message, from_contact ?? null))
  }),

  http.get(url('/disruptions/:id/explanation'), async ({ params, request }) => {
    const plans = await resolvePlans(params.id as string, request)
    return HttpResponse.json(buildExplanation(params.id as string, plans))
  }),

  http.put(url('/recovery-plans/:id'), async ({ params, request }) => {
    const instance = `/recovery-plans/${params.id}`
    const role = userRole(request.headers.get('X-User-Id'))
    if (!role) return problem(401, 'Missing or unknown X-user-id header', instance)
    const base = await resolvePlan(params.id as string, request)
    if (!base) return problem(404, `Recovery plan ${params.id} not found`, instance)
    const body = (await request.json()) as PlanEditRequest
    if (body.base_version !== base.version)
      return problem(409, `Plan ${base.id} is at version ${base.version}, not ${body.base_version}`, instance)
    if (base.status !== 'proposed') return problem(409, `Plan ${base.id} is already ${base.status}`, instance)
    const edited = mockEdit(base, body)
    state.demoPlans[base.id] = edited
    return HttpResponse.json(edited)
  }),

  http.post(url('/recovery-plans/:id/revalidate'), async ({ params, request }) => {
    const base = await resolvePlan(params.id as string, request)
    if (!base) return problem(404, `Recovery plan ${params.id} not found`, `/recovery-plans/${params.id}/revalidate`)
    const refreshed: RecoveryPlan = {
      ...base,
      validation: base.validation && { ...base.validation, validated_at: new Date().toISOString() },
    }
    state.demoPlans[base.id] = refreshed
    return HttpResponse.json(refreshed)
  }),

  http.post(url('/recovery-plans/:id/request-info'), async (ctx) => {
    const plan = await resolvePlan(ctx.params.id as string, ctx.request)
    if (!plan) return problem(404, `Recovery plan ${ctx.params.id} not found`, `/recovery-plans/${ctx.params.id}/request-info`)
    return decide(ctx, plan, 'more_info_requested', 'request-info')
  }),
]

/**
 * Hybrid mode only. After a DEMO-ONLY change (edited plan, mock decision) the real backend does not
 * know about it, so reads of those plans/disruptions are patched here. Everything else passes through.
 */
export const hybridOverlayHandlers: RequestHandler[] = [
  http.get(url('/recovery-plans/:id'), ({ params }) => {
    const p = state.demoPlans[params.id as string]
    return p ? HttpResponse.json(p) : passthrough()
  }),
  http.get(url('/disruptions/:id/recovery-plans'), async ({ params, request }) => {
    const mine = Object.values(state.demoPlans).filter((p) => p.disruption_id === params.id)
    if (mine.length === 0) return passthrough()
    return HttpResponse.json({ items: await resolvePlans(params.id as string, request) })
  }),
  http.post(url('/recovery-plans/:id/approve'), async (ctx) => {
    const p = state.demoPlans[ctx.params.id as string]
    return p ? decide(ctx, p, 'approved', 'approve') : passthrough()
  }),
  http.post(url('/recovery-plans/:id/reject'), async (ctx) => {
    const p = state.demoPlans[ctx.params.id as string]
    return p ? decide(ctx, p, 'rejected', 'reject') : passthrough()
  }),
  http.get(url('/disruptions'), async ({ request }) => {
    if (state.demoDecided.length === 0) return passthrough()
    const real = await fetchReal<{ items: Disruption[] }>('/disruptions', new URL(request.url).origin)
    if (!real) return passthrough()
    return HttpResponse.json({
      items: real.items.map((d) => (state.demoDecided.includes(d.id) ? { ...d, status: 'decided' as const } : d)),
    })
  }),
  http.get(url('/disruptions/:id'), async ({ params, request }) => {
    if (!state.demoDecided.includes(params.id as string)) return passthrough()
    const real = await fetchReal<Disruption>(`/disruptions/${params.id}`, new URL(request.url).origin)
    return real ? HttpResponse.json({ ...real, status: 'decided' as const }) : passthrough()
  }),
]
