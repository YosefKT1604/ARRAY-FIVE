// In-memory mock "database" built from fixtures/demo/*.json. Nothing here is typed by hand:
// all demo content comes from the shared fixtures.
import seed from '../../../fixtures/demo/seed.json'
import incidentFixture from '../../../fixtures/demo/incident.json'
import impactFixture from '../../../fixtures/demo/expected_impact.json'
import plansFixture from '../../../fixtures/demo/expected_plans.json'
import { API_MODE } from '../config'
import noFeasibleScenario from './scenarios/no_feasible.json'
import { getSession } from '../state/session'
import type {
  ActivityLogEntry,
  ActivityType,
  Approval,
  DraftMessage,
  Disruption,
  DisruptionCreate,
  ImpactResult,
  IncomingMessage,
  Incident,
  RecoveryPlan,
} from '../types/contracts'

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v))
const pad = (n: number, w = 3) => String(n).padStart(w, '0')

export const fixtures = {
  seed,
  incident: incidentFixture,
  impact: impactFixture as unknown as ImpactResult,
  plans: plansFixture.plans as unknown as RecoveryPlan[],
  editScenario: plansFixture.edit_scenario,
}

interface MockState {
  disruptions: Disruption[]
  impacts: Record<string, ImpactResult>
  plans: RecoveryPlan[]
  approvals: Approval[]
  /** Demo-only plan versions/statuses (edit, request-info, approvals on edited plans). Latest per plan id. */
  demoPlans: Record<string, RecoveryPlan>
  /** Disruptions decided through a mock approval (hybrid mode patches the real disruption list with these). */
  demoDecided: string[]
  /** Activity entries made by the mock (all of them in mock mode; demo-only ones in hybrid mode). */
  activity: ActivityLogEntry[]
  /** Drafts by plan id (mock only: drafting is Person 5's, not built yet). */
  drafts: Record<string, DraftMessage[]>
  /** WhatsApp messages sent from the simulator (mock mode only), oldest first. */
  inbox: IncomingMessage[]
  counters: { disruption: number; plan: number; approval: number; log: number; draft: number; message: number }
}

function fresh(): MockState {
  return {
    disruptions: [],
    impacts: {},
    plans: [],
    approvals: [],
    demoPlans: {},
    demoDecided: [],
    activity: [],
    drafts: {},
    inbox: [],
    counters: { disruption: 0, plan: 0, approval: 0, log: 0, draft: 0, message: 0 },
  }
}

const STORAGE_KEY = 'scdc.mockState'

/** A page reload mid-demo must not wipe the mock business, so keep it for the tab's lifetime. */
function restore(): MockState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as MockState
      return { ...fresh(), ...saved, counters: { ...fresh().counters, ...saved.counters } }
    }
  } catch {
    /* storage unavailable */
  }
  return fresh()
}

export let state: MockState = restore()

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      /* ignore */
    }
  })
}

/** Back to an empty business, like re-running the backend seed. */
export function resetMockState() {
  state = fresh()
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export function userRole(userId: string | null): 'owner' | 'staff' | 'viewer' | null {
  const user = fixtures.seed.users.find((u) => u.id === userId)
  return (user?.role as 'owner' | 'staff' | 'viewer' | undefined) ?? null
}

export function createMockDisruption(body: DisruptionCreate): { disruption: Disruption; incident: Incident } {
  const id = `D-${pad(++state.counters.disruption)}`
  const reported_at = new Date().toISOString()
  const incident: Incident = {
    schema_version: '1.0',
    id,
    type: body.type,
    source: body.source,
    supplier_id: body.supplier_id ?? null,
    resource_id: body.resource_id ?? null,
    delivery_id: body.delivery_id ?? null,
    quantity_affected: body.quantity_affected ?? null,
    original_arrival_date: body.original_arrival_date ?? null,
    new_arrival_date: body.new_arrival_date ?? null,
    description: body.description,
    reported_at,
    unresolved_fields: [],
  }
  const disruption: Disruption = {
    id,
    type: body.type,
    source: body.source,
    raw_message: body.raw_message ?? null,
    description: body.description,
    reported_at,
    reported_by: 'U-01',
    status: 'received',
    incident,
    severity: null,
  }
  state.disruptions.push(disruption)
  logMock(id, 'disruption_reported', 'system', null, { type: body.type })
  return { disruption, incident }
}

/** Mirrors the backend stub: the fixture impact, re-labelled for this disruption. */
export function analyzeMockDisruption(disruption: Disruption): ImpactResult {
  const impact = clone(fixtures.impact)
  impact.disruption_id = disruption.id
  state.impacts[disruption.id] = impact
  disruption.status = 'analyzed'
  disruption.severity = Math.max(...impact.affected_entities.map((e) => e.severity))
  logMock(disruption.id, 'analysis_completed', 'system', null, { affected_count: impact.affected_entities.length })
  return impact
}

/** The plan templates for the selected mock scenario (A: main demo from fixtures, B: mock-only "no feasible plan"). */
function scenarioPlans(): RecoveryPlan[] {
  if (getSession().scenario !== 'no_feasible') return fixtures.plans
  return (noFeasibleScenario.plans as Record<string, unknown>[]).map((entry) => {
    const ref = entry.use_fixture_plan as string | undefined
    return (ref ? fixtures.plans.find((p) => p.id === ref)! : entry) as unknown as RecoveryPlan
  })
}

/** Mirrors the backend stub: scenario plans with fresh IDs (the counter keeps running across disruptions). */
export function generateMockPlans(disruption: Disruption): RecoveryPlan[] {
  const plans = clone(scenarioPlans()).map((plan) => {
    const id = `RP-${pad(++state.counters.plan)}`
    plan.id = id
    plan.disruption_id = disruption.id
    if (plan.validation) plan.validation.plan_id = id
    return plan
  })
  state.plans.push(...plans)
  disruption.status = 'plans_ready'
  logMock(disruption.id, 'plans_generated', 'system', null, { plan_ids: plans.map((p) => p.id) })
  return plans
}

/** Append to the mock activity log, like the backend's log_activity. */
export function logMock(
  disruptionId: string,
  type: ActivityType,
  actor: string,
  planId: string | null,
  details: Record<string, unknown> = {},
) {
  state.activity.push({
    id: `LOG-${pad(++state.counters.log, 4)}`,
    disruption_id: disruptionId,
    plan_id: planId,
    actor_id: actor,
    activity_type: type,
    // In hybrid mode the real log is authoritative; anything the mock adds is flagged as demo-only.
    details: API_MODE === 'mock' ? details : { ...details, demo_only: true },
    created_at: new Date().toISOString(),
  })
}

export function nextDraftId() {
  return `DM-${pad(++state.counters.draft)}`
}

export function nextMessageId() {
  return `WA-${pad(++state.counters.message)}`
}

export function nextApprovalId() {
  return `AP-${pad(++state.counters.approval)}`
}
