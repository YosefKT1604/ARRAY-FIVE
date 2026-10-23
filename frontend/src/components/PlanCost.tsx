import { isDemoEdit } from '../lib/plans'
import type { RecoveryPlan } from '../types/contracts'
import { MoneyText } from './MoneyText'

/** RM amount, "Cost unknown", or (for a demo-only edit) "Cost will be recalculated". Never RM 0.00. */
export function PlanCost({ plan }: { plan: RecoveryPlan }) {
  if (plan.estimated_cost == null && isDemoEdit(plan)) {
    return <span className="text-muted italic">Cost will be recalculated</span>
  }
  return <MoneyText value={plan.estimated_cost} />
}
