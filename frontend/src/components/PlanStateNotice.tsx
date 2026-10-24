import { Link } from 'react-router-dom'
import type { PlanState } from '../types/contracts'

const NOTICES: Record<PlanState, { text: string; tone: string }> = {
  no_recovery_needed: { text: 'Nothing to recover: no event is affected.', tone: 'border-ok/40 bg-ok-bg text-ok' },
  planning_not_available: {
    text: "We can't suggest plans for this case yet. Check the open questions.",
    tone: 'border-warn/40 bg-warn-bg text-warn',
  },
  impact_unclear: { text: 'The facts are unclear. Confirm them first.', tone: 'border-warn/40 bg-warn-bg text-warn' },
}

/** Why a problem has no recovery plans. Pass `impactLink` (the disruption id) to offer the way back to the impact screen. */
export function PlanStateNotice({ state, impactLink }: { state: PlanState; impactLink?: string }) {
  const notice = NOTICES[state]
  return (
    <div role="status" className={`rounded-2xl border p-4 ${notice.tone}`} data-testid="plan-state-notice">
      <p className="font-semibold">{notice.text}</p>
      {state === 'impact_unclear' && impactLink && (
        <Link to={`/disruptions/${impactLink}/impact`} className="mt-1 inline-block text-sm font-semibold text-brand underline">
          Back to what this affects
        </Link>
      )}
    </div>
  )
}
