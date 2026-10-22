// MOCK-ONLY stand-in for GET /disruptions/{id}/explanation (Person 5 builds the real one).
// Template text assembled from the plans' own data. It never sets or changes a status.
import { formatDate, formatMoney } from '../lib/format'
import type { Explanation, RecoveryPlan } from '../types/contracts'

export function buildExplanation(disruptionId: string, plans: RecoveryPlan[]): Explanation {
  const proposed = plans.filter((p) => p.status !== 'superseded')
  const works = proposed.filter((p) => p.validation?.status === 'feasible').length

  const plan_comparisons = proposed.map((plan) => {
    const arrival = (plan.actions[0]?.parameters as Record<string, unknown> | undefined)?.expected_arrival_date
    const benefits: string[] = []
    if (plan.validation?.status === 'feasible') benefits.push('Every check passed with the data we have.')
    if (plan.estimated_cost) benefits.push(`Costs ${formatMoney(plan.estimated_cost)}.`)
    if (typeof arrival === 'string') benefits.push(`Arrives ${formatDate(arrival)}.`)

    const limitations: string[] = []
    for (const c of plan.validation?.checks ?? []) if (c.result !== 'pass') limitations.push(c.detail)
    limitations.push(...(plan.validation?.unresolved_assumptions ?? []))
    if (!plan.estimated_cost) limitations.push('The cost is not known yet.')

    return {
      plan_id: plan.id,
      validation_status: plan.validation?.status ?? 'needs_confirmation',
      benefits,
      limitations: [...new Set(limitations)],
    }
  })

  const missing = [...new Set(proposed.flatMap((p) => p.validation?.unresolved_assumptions ?? []))]

  return {
    schema_version: '1.0',
    disruption_id: disruptionId,
    summary: `We found ${proposed.length} option${proposed.length === 1 ? '' : 's'}. ${works} ${works === 1 ? 'was' : 'were'} checked as working with the data we have.`,
    impact_explanations: [],
    plan_comparisons,
    missing_confirmations: missing,
    next_steps:
      works > 0
        ? ['Review the recommended option and approve it if it suits you.']
        : ['No option works yet. Confirm the open questions with your suppliers, then check again.'],
    generated_by: 'template',
    fallback_used: true,
    unsupported_claims_removed: 0,
  }
}
