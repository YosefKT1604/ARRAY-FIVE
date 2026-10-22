import { Link } from 'react-router-dom'
import { cn } from '../lib/cn'
import { failingChecks, isDemoEdit, safeBenefits, stillToConfirm } from '../lib/plans'
import { useNames } from '../lib/useNames'
import type { PlanComparison, RecoveryPlan } from '../types/contracts'
import { CheckList } from './CheckList'
import { PlanCost } from './PlanCost'
import { PlanStatusBadge, StatusBadge } from './StatusBadge'

function Bullets({ title, items, tone }: { title: string; items: string[]; tone?: string }) {
  if (items.length === 0) return null
  return (
    <div>
      <p className={cn('text-xs font-semibold tracking-wide uppercase', tone ?? 'text-muted')}>{title}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
        {items.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  )
}

export function PlanCard({
  plan,
  comparison,
  recommended,
}: {
  plan: RecoveryPlan
  comparison?: PlanComparison
  recommended: boolean
}) {
  const names = useNames()
  const status = plan.validation?.status
  const failing = failingChecks(plan)
  const questions = stillToConfirm(plan)
  // Anything already shown as a failing check or an open question is not repeated under "Watch out for".
  const shown = new Set([...failing.map((c) => c.detail), ...questions])
  const watchOut = (comparison?.limitations ?? []).filter((l) => !shown.has(l))
  const benefits = safeBenefits(comparison?.benefits ?? [], plan, names.humanize)

  return (
    <li
      className={cn(
        'flex flex-col gap-3 rounded-2xl border bg-card p-4 sm:p-5',
        recommended ? 'border-brand ring-1 ring-brand/30' : 'border-line',
      )}
      data-plan-id={plan.id}
    >
      <div className="flex flex-wrap items-center gap-2">
        {recommended && <span className="rounded-full bg-brand px-2.5 py-1 text-xs font-semibold text-white">Recommended</span>}
        {status ? (
          <StatusBadge status={status} />
        ) : (
          <span className="rounded-full bg-info-bg px-2.5 py-1 text-xs font-semibold">Not checked yet</span>
        )}
        {plan.status !== 'proposed' && <PlanStatusBadge status={plan.status} />}
        {isDemoEdit(plan) && (
          <span className="rounded-full bg-warn-bg px-2.5 py-1 text-xs font-semibold text-warn">
            Version {plan.version}, edited (demo only)
          </span>
        )}
      </div>

      <div>
        <h3 className="text-lg leading-snug font-semibold">{names.humanize(plan.summary)}</h3>
        <p className="mt-1 text-sm text-muted">
          Cost: <PlanCost plan={plan} />
        </p>
      </div>

      <Bullets title="Good about it" items={benefits} tone="text-ok" />
      <Bullets title="Watch out for" items={watchOut.map(names.humanize)} tone="text-warn" />

      {failing.length > 0 && (
        <div>
          <p className="text-xs font-semibold tracking-wide text-bad uppercase">Why it won't work</p>
          <div className="mt-1">
            <CheckList checks={failing} />
          </div>
        </div>
      )}
      {status === 'needs_confirmation' && questions.length > 0 && (
        <div className="rounded-xl bg-warn-bg p-3">
          <p className="text-xs font-semibold tracking-wide text-warn uppercase">Still to confirm</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
            {questions.map((q) => (
              <li key={q}>{names.humanize(q)}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-auto pt-1">
        <Link
          to={`/plans/${plan.id}`}
          className="inline-flex rounded-xl border border-brand px-4 py-2 text-sm font-semibold text-brand hover:bg-brand hover:text-white"
        >
          {plan.status === 'proposed' ? 'Review this plan' : 'See this plan'}
        </Link>
      </div>
    </li>
  )
}
