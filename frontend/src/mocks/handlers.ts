import { bypass, http, HttpResponse, passthrough, type RequestHandler } from 'msw'
import { API_BASE, API_MODE } from '../config'
import type {
  ActivityLogEntry,
  Approval,
  DecisionRequest,
  Disruption,
  DraftMessage,
  ErrorCode,
  PlanEditRequest,
  RecoveryPlan,
} from '../types/contracts'
import {
  analyzeMockDisruption,
  createMockDisruption,
  fixtures,
  generateMockPlans,
  logMock,
  nextApprovalId,
  nextDraftId,
  state,
  userRole,
} from './db'
import { buildDrafts } from './drafts'
import { mockEdit } from './edit'
import { buildExplanation } from './explanation'
import { mockExtract } from './extract'

const url = (path: string) => `${API_BASE}${path}`

const TITLES: Record<number, string> = {
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not Found',
  409: 'Conflict',
  422: 'Unprocessable Content',
}

/** Same error shape as the real backend: RFC 9457 Problem Details plus a machine-readable `code`. */
function problem(status: number, code: ErrorCode, detail: string, instance: string) {
  return HttpResponse.json(
    { type: 'about:blank', title: TITLES[status] ?? 'Error', status, detail, instance, code },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  )
}

const notFound = (what: string, id: unknown, instance: string) => problem(404, 'NOT_FOUND', `${what} ${id} not found`, instance)

/** Latest demo version of a plan, if the mock has edited or decided it. */
const overlay = (plan: RecoveryPlan): RecoveryPlan => state.demoPlans[plan.id] ?? plan

/** Read from the REAL backend from inside a handler (hybrid mode). */
async function fetchReal<T>(path: string, origin: string): Promise<T | null> {
  const res = await fetch(bypass(new Request(`${origin}${API_BASE}${path}`)))
  return res.ok ? ((await res.json()) as T) : null
}

const originOf = (request: Request) => new URL(request.url).origin

/** Find a plan wherever it lives: demo overlay, mock state, or (hybrid) the real backend. */
async function resolvePlan(id: string, request: Request): Promise<RecoveryPlan | null> {
  if (state.demoPlans[id]) return state.demoPlans[id]
  if (API_MODE === 'mock') return state.plans.find((p) => p.id === id) ?? null
  return fetchReal<RecoveryPlan>(`/recovery-plans/${id}`, originOf(request))
}

async function resolvePlans(disruptionId: string, request: Request): Promise<RecoveryPlan[]> {
  if (API_MODE === 'mock') return state.plans.filter((p) => p.disruption_id === disruptionId).map(overlay)
  const real = await fetchReal<{ items: RecoveryPlan[] }>(`/disruptions/${disruptionId}/recovery-plans`, originOf(request))
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

const DECISION_LOG = { approved: 'plan_approved', rejected: 'plan_rejected', more_info_requested: 'info_requested' } as const

/**
 * Approve / reject / request-info on a plan the MOCK owns. Mirrors the backend's rules
 * (401 unknown user, 403 non-owner and logged as approval_denied, 409 stale version,
 * 409 already decided, 409 infeasible).
 */
async function decide({ request }: Ctx, plan: RecoveryPlan, decision: Decision, verb: string) {
  const instance = `/recovery-plans/${plan.id}/${verb}`
  const userId = request.headers.get('X-User-Id')
  const role = userRole(userId)
  if (!role) return problem(401, 'UNAUTHORIZED', 'Missing or unknown X-user-id header', instance)
  if (role !== 'owner') {
    logMock(plan.disruption_id, 'approval_denied', userId!, plan.id, { role })
    return problem(403, 'FORBIDDEN', `${userId} (${role}) may not approve or reject plans`, instance)
  }
  const body = (await request.json()) as DecisionRequest
  if (body.plan_version !== plan.version)
    return problem(409, 'STALE_PLAN_VERSION', `Plan ${plan.id} is at version ${plan.version}, not ${body.plan_version}`, instance)
  // The backend lets a plan that asked for more info be decided again.
  if (plan.status !== 'proposed' && plan.status !== 'more_info_requested')
    return problem(409, 'INVALID_STATE_TRANSITION', `Plan ${plan.id} is already ${plan.status}`, instance)
  if (decision === 'approved' && (!plan.validation || plan.validation.status === 'infeasible'))
    return problem(409, 'PLAN_INFEASIBLE', `Plan ${plan.id} is infeasible and cannot be approved`, instance)

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
  logMock(plan.disruption_id, DECISION_LOG[decision], userId!, plan.id, { approval_id: approval.id, plan_version: plan.version })
  return HttpResponse.json(approval, { status: 201 })
}

async function decideBuiltIn(ctx: Ctx, decision: Decision, verb: string) {
  const p = state.plans.find((x) => x.id === ctx.params.id)
  if (!p) return notFound('Recovery plan', ctx.params.id, `/recovery-plans/${ctx.params.id}/${verb}`)
  return decide(ctx, overlay(p), decision, verb)
}

/**
 * Mocks of endpoints the real backend HAS built. Registered only in `mock` mode, so the whole
 * demo runs offline. Behaviour mirrors the backend (see INTEGRATION_GAPS.md).
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
        { type: 'about:blank', title: 'Unprocessable Content', status: 422, detail: 'Validation failed', instance: '/disruptions', code: 'VALIDATION_ERROR', errors: fieldProblems },
        { status: 422, headers: { 'Content-Type': 'application/problem+json' } },
      )
    const existing = state.disruptions.find(
      (d) =>
        d.status !== 'closed' &&
        d.incident.delivery_id === (body.delivery_id ?? null) &&
        d.incident.new_arrival_date === (body.new_arrival_date ?? null),
    )
    if (existing)
      return problem(
        409,
        'DUPLICATE_DISRUPTION',
        `Disruption ${existing.id} is already open for delivery ${body.delivery_id} arriving ${body.new_arrival_date}`,
        '/disruptions',
      )
    const { disruption, incident } = createMockDisruption(body)
    return HttpResponse.json({ disruption, incident, validation_errors: [] }, { status: 201 })
  }),
  http.get(url('/disruptions/:id'), ({ params }) => {
    const d = state.disruptions.find((x) => x.id === params.id)
    return d ? HttpResponse.json(d) : notFound('Disruption', params.id, `/disruptions/${params.id}`)
  }),
  http.post(url('/disruptions/:id/analyze'), ({ params }) => {
    const d = state.disruptions.find((x) => x.id === params.id)
    if (!d) return notFound('Disruption', params.id, `/disruptions/${params.id}/analyze`)
    if (d.status === 'needs_clarification')
      return problem(409, 'INVALID_STATE_TRANSITION', 'Disruption needs clarification before it can be analyzed', `/disruptions/${d.id}/analyze`)
    return HttpResponse.json(analyzeMockDisruption(d))
  }),
  http.get(url('/disruptions/:id/impact'), ({ params }) => {
    const impact = state.impacts[params.id as string]
    return impact
      ? HttpResponse.json(impact)
      : problem(404, 'NOT_FOUND', `Disruption ${params.id} has not been analyzed yet`, `/disruptions/${params.id}/impact`)
  }),
  http.post(url('/disruptions/:id/recovery-plans'), ({ params }) => {
    const d = state.disruptions.find((x) => x.id === params.id)
    if (!d) return notFound('Disruption', params.id, `/disruptions/${params.id}/recovery-plans`)
    if (d.status !== 'analyzed')
      return problem(409, 'INVALID_STATE_TRANSITION', `Plans need an analyzed disruption; ${d.id} is ${d.status}`, `/disruptions/${d.id}/recovery-plans`)
    return HttpResponse.json({ items: generateMockPlans(d) }, { status: 201 })
  }),
  http.get(url('/disruptions/:id/recovery-plans'), ({ params }) =>
    HttpResponse.json({ items: state.plans.filter((p) => p.disruption_id === params.id).map(overlay) }),
  ),
  http.get(url('/disruptions/:id/activity-log'), ({ params }) => {
    if (!state.disruptions.some((d) => d.id === params.id)) return notFound('Disruption', params.id, `/disruptions/${params.id}/activity-log`)
    return HttpResponse.json({ items: state.activity.filter((a) => a.disruption_id === params.id) })
  }),
  http.get(url('/recovery-plans/:id'), ({ params }) => {
    const p = state.plans.find((x) => x.id === params.id)
    return p ? HttpResponse.json(overlay(p)) : notFound('Recovery plan', params.id, `/recovery-plans/${params.id}`)
  }),
  http.post(url('/recovery-plans/:id/approve'), (ctx) => decideBuiltIn(ctx, 'approved', 'approve')),
  http.post(url('/recovery-plans/:id/reject'), (ctx) => decideBuiltIn(ctx, 'rejected', 'reject')),
  http.post(url('/recovery-plans/:id/request-info'), (ctx) => decideBuiltIn(ctx, 'more_info_requested', 'request-info')),
]

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
    const userId = request.headers.get('X-User-Id')
    if (!userRole(userId)) return problem(401, 'UNAUTHORIZED', 'Missing or unknown X-user-id header', instance)
    const base = await resolvePlan(params.id as string, request)
    if (!base) return notFound('Recovery plan', params.id, instance)
    const body = (await request.json()) as PlanEditRequest
    if (body.base_version !== base.version)
      return problem(409, 'STALE_PLAN_VERSION', `Plan ${base.id} is at version ${base.version}, not ${body.base_version}`, instance)
    if (base.status !== 'proposed' && base.status !== 'more_info_requested')
      return problem(409, 'INVALID_STATE_TRANSITION', `Plan ${base.id} is already ${base.status}`, instance)
    const edited = mockEdit(base, body)
    state.demoPlans[base.id] = edited
    logMock(base.disruption_id, 'plan_edited', userId!, base.id, { from_version: base.version, to_version: edited.version })
    return HttpResponse.json(edited)
  }),

  /** Demo-only (not in CONTRACTS.md): throw away the mock edit and go back to the plan the backend knows. */
  http.delete(url('/recovery-plans/:id/demo-edit'), async ({ params, request }) => {
    const id = params.id as string
    delete state.demoPlans[id]
    const original = API_MODE === 'mock' ? state.plans.find((p) => p.id === id) : await fetchReal<RecoveryPlan>(`/recovery-plans/${id}`, originOf(request))
    return original ? HttpResponse.json(original) : notFound('Recovery plan', id, `/recovery-plans/${id}/demo-edit`)
  }),

  http.post(url('/recovery-plans/:id/revalidate'), async ({ params, request }) => {
    const base = await resolvePlan(params.id as string, request)
    if (!base) return notFound('Recovery plan', params.id, `/recovery-plans/${params.id}/revalidate`)
    const refreshed: RecoveryPlan = {
      ...base,
      validation: base.validation && { ...base.validation, validated_at: new Date().toISOString() },
    }
    state.demoPlans[base.id] = refreshed
    logMock(base.disruption_id, 'plan_revalidated', request.headers.get('X-User-Id') ?? 'system', base.id, { version: base.version })
    return HttpResponse.json(refreshed)
  }),

  /** Drafting is Person 5's job. Idempotent here: asking twice returns the same drafts. Only for approved plans. */
  http.post(url('/recovery-plans/:id/drafts'), async ({ params, request }) => {
    const instance = `/recovery-plans/${params.id}/drafts`
    const plan = await resolvePlan(params.id as string, request)
    if (!plan) return notFound('Recovery plan', params.id, instance)
    if (plan.status !== 'approved')
      return problem(409, 'INVALID_STATE_TRANSITION', `Drafts can only be made for an approved plan; ${plan.id} is ${plan.status}`, instance)
    if (!state.drafts[plan.id]) {
      state.drafts[plan.id] = buildDrafts(plan).map((d): DraftMessage => ({ ...d, id: nextDraftId() }))
      logMock(plan.disruption_id, 'draft_created', request.headers.get('X-User-Id') ?? 'system', plan.id, { draft_ids: state.drafts[plan.id].map((d) => d.id) })
    }
    return HttpResponse.json({ items: state.drafts[plan.id] }, { status: 201 })
  }),

  http.post(url('/drafts/:id/approve'), async ({ params, request }) => {
    const instance = `/drafts/${params.id}/approve`
    const userId = request.headers.get('X-User-Id')
    const role = userRole(userId)
    if (!role) return problem(401, 'UNAUTHORIZED', 'Missing or unknown X-user-id header', instance)
    const draft = Object.values(state.drafts).flat().find((d) => d.id === params.id)
    if (!draft) return notFound('Draft', params.id, instance)
    if (role !== 'owner') return problem(403, 'FORBIDDEN', `${userId} (${role}) may not approve drafts`, instance)
    draft.status = 'approved' // approved is not sent: nothing in this app sends anything
    const plan = (await resolvePlan(draft.plan_id, request)) ?? undefined
    if (plan) logMock(plan.disruption_id, 'draft_approved', userId!, plan.id, { draft_id: draft.id })
    return HttpResponse.json(draft)
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
  http.post(url('/recovery-plans/:id/request-info'), async (ctx) => {
    const p = state.demoPlans[ctx.params.id as string]
    return p ? decide(ctx, p, 'more_info_requested', 'request-info') : passthrough()
  }),
  // The real log is authoritative; demo-only events (edits, drafts, mock decisions) are added on top.
  http.get(url('/disruptions/:id/activity-log'), async ({ params, request }) => {
    const mine = state.activity.filter((a) => a.disruption_id === params.id)
    if (mine.length === 0) return passthrough()
    const real = await fetchReal<{ items: ActivityLogEntry[] }>(`/disruptions/${params.id}/activity-log`, originOf(request))
    const items = [...(real?.items ?? []), ...mine].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
    return HttpResponse.json({ items })
  }),
  http.get(url('/disruptions'), async ({ request }) => {
    if (state.demoDecided.length === 0) return passthrough()
    const real = await fetchReal<{ items: Disruption[] }>('/disruptions', originOf(request))
    if (!real) return passthrough()
    return HttpResponse.json({
      items: real.items.map((d) => (state.demoDecided.includes(d.id) ? { ...d, status: 'decided' as const } : d)),
    })
  }),
  http.get(url('/disruptions/:id'), async ({ params, request }) => {
    if (!state.demoDecided.includes(params.id as string)) return passthrough()
    const real = await fetchReal<Disruption>(`/disruptions/${params.id}`, originOf(request))
    return real ? HttpResponse.json({ ...real, status: 'decided' as const }) : passthrough()
  }),
]
