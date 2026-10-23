import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getDashboard } from '../api/endpoints'
import { DisruptionStatusBadge, StatusBadge } from '../components/StatusBadge'
import { PlanCost } from '../components/PlanCost'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary, card } from '../components/ui'
import { formatDate, relativeDay, relativeTime } from '../lib/format'
import { useNames } from '../lib/useNames'
import type { Disruption, PendingDecision } from '../types/contracts'

function nextStepLink(d: Disruption): { to: string; label: string } {
  switch (d.status) {
    case 'plans_ready':
      return { to: `/disruptions/${d.id}/plans`, label: 'Review plans' }
    case 'decided':
      return { to: `/disruptions/${d.id}/plans`, label: 'See decision' }
    default:
      return { to: `/disruptions/${d.id}/impact`, label: 'See impact' }
  }
}

/** "1 works, 1 needs confirmation, 1 won't work", counted from the statuses the API returned. */
function optionSummary(plans: PendingDecision['plans']): string {
  const count = (s: string) => plans.filter((p) => p.validation?.status === s).length
  const parts = [
    [count('feasible'), 'works'],
    [count('needs_confirmation'), 'needs confirmation'],
    [count('infeasible'), "won't work"],
  ]
    .filter(([n]) => (n as number) > 0)
    .map(([n, t]) => `${n} ${t}`)
  return `${plans.length} option${plans.length === 1 ? '' : 's'}${parts.length ? ` (${parts.join(', ')})` : ''}`
}

function DecisionCard({ item }: { item: PendingDecision }) {
  const names = useNames()
  const { disruption, plans, recommended } = item
  const supplier = disruption.incident.supplier_id ? names.supplier(disruption.incident.supplier_id) : undefined
  const resource = disruption.incident.resource_id ? names.resource(disruption.incident.resource_id) : undefined
  const title =
    supplier && resource ? `${supplier.aliases?.[0] ?? supplier.name} ${resource.unit} delay` : names.humanize(disruption.description)

  return (
    <li className={card} data-testid="decision-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">{title}</p>
          <p className="text-sm text-muted">{optionSummary(plans)}</p>
        </div>
        <Link to={`/disruptions/${disruption.id}/plans`} className={btnPrimary}>
          Choose a plan
        </Link>
      </div>
      {recommended && (
        <div className="mt-3 rounded-xl bg-paper p-3">
          <p className="text-xs font-semibold tracking-wide text-brand uppercase">Recommended</p>
          <p className="mt-0.5 font-medium">{names.humanize(recommended.summary)}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            {recommended.validation && <StatusBadge status={recommended.validation.status} />}
            <span>
              Cost: <PlanCost plan={recommended} />
            </span>
          </p>
        </div>
      )}
    </li>
  )
}

export function Dashboard() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard })
  const names = useNames()

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Today at Seri Kenanga Events</h1>
          <p className="mt-1 text-muted">What's coming up, what's gone wrong, and what needs your decision.</p>
        </div>
        <Link to="/report" className={btnPrimary}>
          Report a problem
        </Link>
      </section>

      {isLoading && <LoadingState label="Loading your dashboard…" />}
      {error && <ErrorPanel error={error} onRetry={() => void refetch()} />}

      {data && (
        <>
          <section aria-labelledby="pending">
            <h2 id="pending" className="mb-3 text-xl font-semibold">
              Waiting for your decision
            </h2>
            {data.pending_decisions.length === 0 ? (
              <EmptyState title="Nothing waiting for a decision">When a problem has recovery options ready, they'll show up here.</EmptyState>
            ) : (
              <ul className="space-y-3">
                {data.pending_decisions.map((item) => (
                  <DecisionCard key={item.disruption.id} item={item} />
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="active">
            <h2 id="active" className="mb-3 text-xl font-semibold">
              Active problems
            </h2>
            {data.active_disruptions.length === 0 ? (
              <EmptyState title="No problems reported">All clear. If a supplier lets you down, use "Report a problem".</EmptyState>
            ) : (
              <ul className="space-y-3">
                {data.active_disruptions.map((d) => {
                  const next = nextStepLink(d)
                  return (
                    <li key={d.id} className={card}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{names.humanize(d.description)}</p>
                          <p className="mt-1 text-sm text-muted">Reported {relativeTime(d.reported_at)}</p>
                        </div>
                        <div className="flex items-center gap-3">
                          <DisruptionStatusBadge status={d.status} />
                          <Link to={next.to} className="text-sm font-semibold text-brand underline">
                            {next.label}
                          </Link>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section aria-labelledby="upcoming">
            <h2 id="upcoming" className="mb-3 text-xl font-semibold">
              Upcoming events
            </h2>
            {data.upcoming_jobs.length === 0 ? (
              <EmptyState title="No upcoming events" />
            ) : (
              <ul className="grid gap-3 sm:grid-cols-3">
                {data.upcoming_jobs.map((job) => (
                  <li key={job.id} className={card}>
                    <p className="text-sm font-semibold text-brand">
                      {formatDate(job.event_date)} <span className="font-normal text-muted">· {relativeDay(job.event_date)}</span>
                    </p>
                    <p className="mt-1 font-medium">{job.name}</p>
                    {job.description && <p className="mt-1 text-sm text-muted">{job.description}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}
