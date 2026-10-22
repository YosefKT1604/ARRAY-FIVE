import { cn } from '../lib/cn'
import type { DisruptionStatus, PlanStatus, ValidationStatus } from '../types/contracts'

const base = 'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap'

// Rule 3: green only when the API says feasible; never present unchecked plans as working.
const VALIDATION: Record<ValidationStatus, { label: string; tone: string; icon: string }> = {
  feasible: { label: 'Checked: works with known data', tone: 'bg-ok-bg text-ok', icon: '✓' },
  needs_confirmation: { label: 'Needs confirmation', tone: 'bg-warn-bg text-warn', icon: '?' },
  infeasible: { label: "Won't work", tone: 'bg-bad-bg text-bad', icon: '✕' },
}

export function StatusBadge({ status, className }: { status: ValidationStatus; className?: string }) {
  const s = VALIDATION[status]
  return (
    <span className={cn(base, s.tone, className)} data-status={status}>
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </span>
  )
}

const DISRUPTION: Record<DisruptionStatus, string> = {
  received: 'Reported',
  needs_clarification: 'Needs details',
  validated: 'Details checked',
  analyzed: 'Impact assessed',
  plans_ready: 'Plans ready',
  decided: 'Decision made',
  closed: 'Closed',
}

export function DisruptionStatusBadge({ status }: { status: DisruptionStatus }) {
  const tone =
    status === 'needs_clarification'
      ? 'bg-warn-bg text-warn'
      : status === 'decided' || status === 'closed'
        ? 'bg-ok-bg text-ok'
        : 'bg-info-bg text-ink'
  return <span className={cn(base, tone)}>{DISRUPTION[status]}</span>
}

const PLAN: Record<PlanStatus, string> = {
  proposed: 'Awaiting decision',
  approved: 'Approved',
  rejected: 'Rejected',
  more_info_requested: 'More info requested',
  superseded: 'Replaced by a newer version',
}

export function PlanStatusBadge({ status }: { status: PlanStatus }) {
  const tone =
    status === 'approved' ? 'bg-ok-bg text-ok' : status === 'rejected' ? 'bg-bad-bg text-bad' : 'bg-info-bg text-ink'
  return <span className={cn(base, tone)}>{PLAN[status]}</span>
}
