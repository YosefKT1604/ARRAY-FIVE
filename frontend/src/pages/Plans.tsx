import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/errors'
import { generatePlans, getDisruption, getExplanation, listPlans } from '../api/endpoints'
import { AiBadge } from '../components/AiBadge'
import { PlanCard } from '../components/PlanCard'
import { PlanStateNotice } from '../components/PlanStateNotice'
import { DisruptionStatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary } from '../components/ui'
import { API_MODE } from '../config'
import { sortByRank } from '../lib/plans'
import { useNames } from '../lib/useNames'
import type { PlanState } from '../types/contracts'

export function Plans() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const names = useNames()

  const disruption = useQuery({ queryKey: ['disruption', id], queryFn: () => getDisruption(id) })
  const plans = useQuery({ queryKey: ['plans', id], queryFn: () => listPlans(id) })
  // The explanation is a labelled mock until Person 5 ships it; failing to load it must not block the plans.
  const explanation = useQuery({ queryKey: ['explanation', id], queryFn: () => getExplanation(id) })

  const generate = useMutation({
    mutationFn: () => generatePlans(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['plans', id] })
      void queryClient.invalidateQueries({ queryKey: ['disruption', id] })
      void queryClient.invalidateQueries({ queryKey: ['explanation', id] })
    },
    // A refusal is remembered by the backend; reload so the screen shows it the same way as on a later visit.
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ['plans', id] })
      void queryClient.invalidateQueries({ queryKey: ['disruption', id] })
    },
  })

  if (disruption.isLoading || plans.isLoading) return <LoadingState label="Loading options…" />
  if (disruption.error) return <ErrorPanel error={disruption.error} onRetry={() => void disruption.refetch()} />
  if (plans.error) return <ErrorPanel error={plans.error} onRetry={() => void plans.refetch()} />

  const d = disruption.data!
  const list = sortByRank(plans.data!.items.filter((p) => p.status !== 'superseded'))
  // The backend's reason for having no plans; a refusal to plan arrives as an error before it can be listed.
  const refused = generate.error instanceof ApiError && generate.error.isImpactUnclear
  const state: PlanState | null = plans.data!.state ?? d.plan_state ?? (refused ? 'impact_unclear' : null)
  const anyWorks = list.some((p) => p.validation?.status === 'feasible')
  const ex = explanation.data
  const compare = (planId: string) => ex?.plan_comparisons.find((c) => c.plan_id === planId)

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/disruptions/${id}/impact`} className="text-sm font-semibold text-brand underline">
          ← What this affects
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold">Recovery options</h1>
          <DisruptionStatusBadge status={d.status} />
        </div>
        <p className="mt-1 text-muted">{names.humanize(d.description)}</p>
      </div>

      {list.length === 0 && state && <PlanStateNotice state={state} impactLink={id} />}

      {list.length === 0 && !state && (
        <div className="space-y-3">
          <EmptyState title="No options yet">
            {d.status === 'analyzed' ? 'Ask us to find ways to fix this.' : 'Check the impact first, then come back.'}
          </EmptyState>
          {d.status === 'analyzed' && (
            <button className={btnPrimary} disabled={generate.isPending} onClick={() => generate.mutate()}>
              {generate.isPending ? 'Finding options…' : 'Find recovery options'}
            </button>
          )}
          {generate.error && <ErrorPanel error={generate.error} />}
        </div>
      )}

      {list.length > 0 && !anyWorks && (
        <section className="rounded-2xl border border-warn/40 bg-warn-bg p-5" role="status">
          <h2 className="text-xl font-semibold text-warn">No plan works yet. Here's what to check next</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {(ex?.next_steps.length ? ex.next_steps : ['Confirm the open questions on each option with your suppliers.']).map((t) => (
              <li key={t}>{names.humanize(t)}</li>
            ))}
            {ex?.missing_confirmations.map((t) => <li key={t}>{names.humanize(t)}</li>)}
          </ul>
        </section>
      )}

      {ex && list.length > 0 && (
        <div className="rounded-xl bg-info-bg p-4 text-sm">
          <p>
            {names.humanize(ex.summary)} <AiBadge generatedBy={ex.generated_by} />
          </p>
          {API_MODE === 'mock' && (
            <p className="mt-1 text-muted">Mock mode: these notes are simulated template text.</p>
          )}
        </div>
      )}

      {list.length > 0 && (
        <ul className="grid gap-4 lg:grid-cols-3">
          {list.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              comparison={compare(plan.id)}
              recommended={plan.rank === 1 && plan.validation?.status !== 'infeasible'}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
