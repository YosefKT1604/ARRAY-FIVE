import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getActivityLog, getDisruption, listPlans } from '../api/endpoints'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { card } from '../components/ui'
import { API_MODE } from '../config'
import { actorName, describeActivity } from '../lib/activity'
import { formatTimeOfDay } from '../lib/format'
import { useNames } from '../lib/useNames'

export function ActivityLog() {
  const { id = '' } = useParams()
  const names = useNames()

  const disruption = useQuery({ queryKey: ['disruption', id], queryFn: () => getDisruption(id) })
  const log = useQuery({ queryKey: ['activity', id], queryFn: () => getActivityLog(id) })
  // Plan titles make the sentences readable; the log still works without them.
  const plans = useQuery({ queryKey: ['plans', id], queryFn: () => listPlans(id) })

  if (log.isLoading || disruption.isLoading) return <LoadingState label="Loading the activity log…" />
  if (disruption.error) return <ErrorPanel error={disruption.error} onRetry={() => void disruption.refetch()} />
  if (log.error) return <ErrorPanel error={log.error} onRetry={() => void log.refetch()} />

  const planTitle = (planId: string | null) => plans.data?.items.find((p) => p.id === planId)?.summary
  const items = log.data?.items ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link to={`/disruptions/${id}/impact`} className="text-sm font-semibold text-brand underline">
          ← What this affects
        </Link>
        <h1 className="mt-2 text-3xl font-semibold">Activity log</h1>
        <p className="mt-1 text-muted">Everything that has happened on this problem, oldest first.</p>
      </div>

      {items.length === 0 ? (
        <EmptyState title="Nothing has happened yet">Actions on this problem will be listed here.</EmptyState>
      ) : (
        <ol className="relative space-y-4 border-l-2 border-line pl-6" aria-label="Timeline">
          {items.map((entry) => {
            const demoOnly = entry.details.demo_only === true
            const denied = entry.activity_type === 'approval_denied'
            return (
              <li key={entry.id} className={card} data-activity={entry.activity_type}>
                <span
                  aria-hidden
                  className={`absolute -left-[9px] mt-1.5 size-4 rounded-full border-2 border-paper ${denied ? 'bg-bad' : 'bg-brand'}`}
                />
                <p className="text-base">
                  {describeActivity(entry, {
                    planTitle,
                    humanize: names.humanize,
                    disruptionDescription: disruption.data?.description,
                  })}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
                  <span>{formatTimeOfDay(entry.created_at)}</span>
                  {demoOnly && API_MODE !== 'mock' && (
                    <span className="rounded-full bg-warn-bg px-2 py-0.5 text-xs font-semibold text-warn">Demo only</span>
                  )}
                </p>
                <details className="mt-2 text-xs text-muted">
                  <summary className="cursor-pointer">Details</summary>
                  <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                    <dt>Entry</dt>
                    <dd>{entry.id}</dd>
                    <dt>Type</dt>
                    <dd>{entry.activity_type}</dd>
                    <dt>Who</dt>
                    <dd>
                      {actorName(entry.actor_id)} ({entry.actor_id})
                    </dd>
                    {entry.plan_id && (
                      <>
                        <dt>Plan</dt>
                        <dd>{entry.plan_id}</dd>
                      </>
                    )}
                    <dt>Data</dt>
                    <dd className="break-all">{JSON.stringify(entry.details)}</dd>
                  </dl>
                </details>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
