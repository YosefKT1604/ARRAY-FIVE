// MOCK-ONLY stand-in for PUT /recovery-plans/{id} (editing) and its revalidation.
// The frontend must not validate plans itself (CLAUDE.md rule 2), so this does NOT compute anything:
// it replays the one scripted case from fixtures/demo/expected_plans.json (edit_scenario) and returns
// "needs confirmation" for every other edit.
import type { Check, PlanEditRequest, RecoveryPlan, ValidationResult } from '../types/contracts'
import { fixtures } from './db'

type Params = Record<string, unknown>
const paramsOf = (plan: Pick<RecoveryPlan, 'actions'>): Params => (plan.actions[0]?.parameters ?? {}) as Params

export const MOCK_CANNOT_VALIDATE = 'Mock mode cannot validate this edit'

/** Is this the scripted "20 -> 10 chairs from Cahaya" edit? Matched by content, since plan IDs change per run. */
function isScriptedEdit(base: RecoveryPlan, edit: PlanEditRequest): boolean {
  const fx = paramsOf(fixtures.plans[0])
  const before = paramsOf(base)
  const after = paramsOf({ actions: edit.actions })
  return (
    before.supplier_id === fx.supplier_id &&
    before.resource_id === fx.resource_id &&
    before.quantity === fx.quantity &&
    after.quantity === fixtures.editScenario.changed_parameter.quantity
  )
}

/** Keep the title honest after an edit: swap each changed quantity in the summary (20 -> 10). */
function retitle(summary: string, before: RecoveryPlan['actions'], after: RecoveryPlan['actions']): string {
  let text = summary
  before.forEach((a, i) => {
    const was = (a.parameters as Params).quantity
    const now = (after[i]?.parameters as Params | undefined)?.quantity
    if (typeof was === 'number' && typeof now === 'number' && was !== now) {
      text = text.replace(new RegExp(`(^|[^0-9])${was}([^0-9]|$)`), `$1${now}$2`)
    }
  })
  return text
}

export function mockEdit(base: RecoveryPlan, edit: PlanEditRequest): RecoveryPlan {
  const version = base.version + 1
  const validated_at = new Date().toISOString()

  let validation: ValidationResult
  if (isScriptedEdit(base, edit)) {
    const failing = fixtures.editScenario.expected_failed_checks
    const checks: Check[] = (fixtures.plans[0].validation?.checks ?? []).map((c) =>
      failing.includes(c.code) ? { ...c, result: 'fail', detail: fixtures.editScenario.expected_detail } : c,
    )
    validation = { plan_id: base.id, plan_version: version, status: 'infeasible', checks, unresolved_assumptions: [], validated_at }
  } else {
    validation = {
      plan_id: base.id,
      plan_version: version,
      status: 'needs_confirmation',
      checks: [{ code: 'FACTS_KNOWN', result: 'unresolved', detail: `${MOCK_CANNOT_VALIDATE}.`, evidence_ids: [] }],
      unresolved_assumptions: [MOCK_CANNOT_VALIDATE],
      validated_at,
    }
  }

  return {
    ...base,
    version,
    summary: retitle(base.summary, base.actions, edit.actions),
    actions: edit.actions,
    assumptions: edit.assumptions,
    // Cost would have to be recalculated by the backend, so it is unknown here (never RM 0.00).
    estimated_cost: null,
    validation,
    rank: null,
    status: 'proposed',
    created_by: 'user_edit',
  }
}
