// In-memory mock "database" built from fixtures/demo/*.json. Nothing here is typed by hand:
// all demo content comes from the shared fixtures.
import seed from '../../../fixtures/demo/seed.json'
import incidentFixture from '../../../fixtures/demo/incident.json'
import impactFixture from '../../../fixtures/demo/expected_impact.json'
import plansFixture from '../../../fixtures/demo/expected_plans.json'
import type {
  Approval,
  Disruption,
  DisruptionCreate,
  ImpactResult,
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
  counters: { disruption: number; plan: number; approval: number }
}

function fresh(): MockState {
  return {
    disruptions: [],
    impacts: {},
    plans: [],
    approvals: [],
    counters: { disruption: 0, plan: 0, approval: 0 },
  }
}

export let state: MockState = fresh()

/** Back to an empty business, like re-running the backend seed. */
export function resetMockState() {
  state = fresh()
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
  return { disruption, incident }
}

/** Mirrors the backend stub: the fixture impact, re-labelled for this disruption. */
export function analyzeMockDisruption(disruption: Disruption): ImpactResult {
  const impact = clone(fixtures.impact)
  impact.disruption_id = disruption.id
  state.impacts[disruption.id] = impact
  disruption.status = 'analyzed'
  disruption.severity = Math.max(...impact.affected_entities.map((e) => e.severity))
  return impact
}

/** Mirrors the backend stub: fixture plans with fresh IDs (the counter keeps running across disruptions). */
export function generateMockPlans(disruption: Disruption): RecoveryPlan[] {
  const plans = clone(fixtures.plans).map((plan) => {
    const id = `RP-${pad(++state.counters.plan)}`
    plan.id = id
    plan.disruption_id = disruption.id
    if (plan.validation) plan.validation.plan_id = id
    return plan
  })
  state.plans.push(...plans)
  disruption.status = 'plans_ready'
  return plans
}

export function nextApprovalId() {
  return `AP-${pad(++state.counters.approval)}`
}
