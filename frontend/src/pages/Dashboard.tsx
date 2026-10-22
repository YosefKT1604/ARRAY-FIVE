import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getDashboard } from '../api/endpoints'
import { DisruptionStatusBadge, StatusBadge } from '../components/StatusBadge'
import { MoneyText } from '../components/MoneyText'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { formatDate, formatDateTime } from '../lib/format'
import type { Disruption } from '../types/contracts'

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

const card = 'rounded-2xl border border-line bg-card p-4 sm:p-5'

export function Dashboard() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard })

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Today at Seri Kenanga Events</h1>
          <p className="mt-1 text-muted">What's coming up, what's gone wrong, and what needs your decision.</p>
        </div>
        <Link
          to="/report"
          className="rounded-xl bg-brand px-5 py-3 text-base font-semibold text-white shadow-sm hover:bg-brand-dark"
        >
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
            {data.pending_approvals.length === 0 ? (
              <EmptyState title="Nothing waiting for approval">
                When a problem has recovery plans ready, they'll show up here.
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {data.pending_approvals.map(({ disruption, plan }) => (
                  <li key={plan.id} className={card}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{plan.summary}</p>
                        <p className="mt-1 text-sm text-muted">
                          For: {disruption.description} · Cost: <MoneyText value={plan.estimated_cost} />
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        {plan.validation && <StatusBadge status={plan.validation.status} />}
                        <Link to={`/plans/${plan.id}`} className="text-sm font-semibold text-brand underline">
                          Review
                        </Link>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="active">
            <h2 id="active" className="mb-3 text-xl font-semibold">
              Active problems
            </h2>
            {data.active_disruptions.length === 0 ? (
              <EmptyState title="No problems reported">
                All clear. If a supplier lets you down, use "Report a problem".
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {data.active_disruptions.map((d) => {
                  const next = nextStepLink(d)
                  return (
                    <li key={d.id} className={card}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{d.description}</p>
                          <p className="mt-1 text-sm text-muted">Reported {formatDateTime(d.reported_at)}</p>
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
                    <p className="text-sm font-semibold text-brand">{formatDate(job.event_date)}</p>
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
