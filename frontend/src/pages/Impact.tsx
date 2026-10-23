import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/errors'
import { analyzeDisruption, generatePlans, getDisruption, getImpact } from '../api/endpoints'
import { DependencyPath } from '../components/DependencyPath'
import { PlanStateNotice } from '../components/PlanStateNotice'
import { DisruptionStatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary, card } from '../components/ui'
import { cn } from '../lib/cn'
import { formatDate } from '../lib/format'
import { KIND_LABEL, useNames } from '../lib/useNames'
import type { AffectedEntity, ImpactResult } from '../types/contracts'

const IMPACT_BADGE: Record<AffectedEntity['impact_status'], { label: string; tone: string }> = {
  confirmed: { label: 'Affected', tone: 'bg-bad-bg text-bad' },
  potential_risk: { label: 'Possible risk', tone: 'bg-warn-bg text-warn' },
  unresolved: { label: "Not sure yet", tone: 'bg-info-bg text-ink' },
}

function Shortfalls({ impact }: { impact: ImpactResult }) {
  const names = useNames()
  if (impact.resource_shortfalls.length === 0) return null
  return (
    <div className="space-y-3">
      {impact.resource_shortfalls.map((s) => {
        const r = names.resource(s.resource_id)
        const unit = r ? `${r.unit}${s.shortfall === 1 ? '' : 's'}` : 'units'
        return (
          <div key={`${s.resource_id}-${s.date}`} className="rounded-2xl border border-bad/30 bg-bad-bg p-5">
            <p className="text-sm font-semibold tracking-wide text-bad uppercase">Shortfall</p>
            <p className="mt-1 font-display text-3xl font-semibold text-bad">
              Short {s.shortfall} {unit} on {formatDate(s.date)}
            </p>
            <p className="mt-1 text-ink">
              You need {s.required}, but only {s.available} will be available.
            </p>
          </div>
        )
      })}
    </div>
  )
}

function AffectedCard({ item }: { item: AffectedEntity }) {
  const names = useNames()
  const badge = IMPACT_BADGE[item.impact_status]
  const kind = names.kindOf(item.entity_id, item.entity_type)
  return (
    <li className={card}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          {kind && <p className="text-[11px] font-semibold tracking-wide text-muted uppercase">{KIND_LABEL[kind]}</p>}
          <p className="text-lg font-semibold">{names.label(item.entity_id, item.entity_type)}</p>
        </div>
        <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', badge.tone)}>{badge.label}</span>
      </div>
      <p className="mt-2">{names.humanize(item.reason)}</p>
      <div className="mt-3">
        <DependencyPath path={item.dependency_path} />
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-muted">Details</summary>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-muted">Original text</dt>
          <dd>{item.reason}</dd>
          <dt className="text-muted">ID</dt>
          <dd>{item.entity_id}</dd>
          <dt className="text-muted">Status code</dt>
          <dd>{item.impact_status}</dd>
          <dt className="text-muted">Severity</dt>
          <dd>{item.severity} / 10</dd>
          {item.evidence.map((e) => (
            <div key={`${e.entity_id}-${e.fact}`} className="contents">
              <dt className="text-muted">Evidence ({e.entity_id})</dt>
              <dd>{e.fact}</dd>
            </div>
          ))}
        </dl>
      </details>
    </li>
  )
}

export function Impact() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const names = useNames()

  const disruption = useQuery({ queryKey: ['disruption', id], queryFn: () => getDisruption(id) })
  const impact = useQuery({
    queryKey: ['impact', id],
    queryFn: () => getImpact(id),
    // 404 just means "not analysed yet"
    retry: false,
  })

  const analyze = useMutation({
    mutationFn: () => analyzeDisruption(id),
    onSuccess: (result) => {
      queryClient.setQueryData(['impact', id], result)
      void queryClient.invalidateQueries({ queryKey: ['disruption', id] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const plans = useMutation({
    mutationFn: () => generatePlans(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['disruption', id] })
      void queryClient.invalidateQueries({ queryKey: ['plans', id] })
      navigate(`/disruptions/${id}/plans`)
    },
  })

  if (disruption.isLoading) return <LoadingState label="Loading…" />
  if (disruption.error) return <ErrorPanel error={disruption.error} onRetry={() => void disruption.refetch()} />
  const d = disruption.data!

  const notAnalysed = impact.error instanceof ApiError && impact.error.status === 404
  const otherError = impact.error && !notAnalysed ? impact.error : null
  const data = impact.data

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm font-semibold text-brand underline">
          ← Dashboard
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold">What this affects</h1>
          <DisruptionStatusBadge status={d.status} />
        </div>
        <p className="mt-1 text-muted">{names.humanize(d.description)}</p>
      </div>

      {impact.isLoading && <LoadingState label="Checking what's affected…" />}
      {otherError && <ErrorPanel error={otherError} onRetry={() => void impact.refetch()} />}

      {notAnalysed && (
        <div className={cn(card, 'space-y-3')}>
          <p className="font-semibold">We haven't checked the impact of this problem yet.</p>
          <button className={btnPrimary} disabled={analyze.isPending} onClick={() => analyze.mutate()}>
            {analyze.isPending ? 'Checking…' : 'Check impact'}
          </button>
          {analyze.error && <ErrorPanel error={analyze.error} />}
        </div>
      )}

      {data && (
        <>
          <Shortfalls impact={data} />

          <section aria-labelledby="affected" className="space-y-3">
            <h2 id="affected" className="text-xl font-semibold">
              Affected
            </h2>
            {data.affected_entities.length === 0 ? (
              <EmptyState title="Nothing affected">We found no events or commitments that depend on this.</EmptyState>
            ) : (
              <ul className="space-y-3">
                {data.affected_entities.map((item) => (
                  <AffectedCard key={`${item.entity_type}-${item.entity_id}`} item={item} />
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="clear" className="space-y-3">
            <h2 id="clear" className="text-xl font-semibold">
              Checked, not affected
            </h2>
            {data.checked_not_affected.length === 0 ? (
              <EmptyState title="Nothing else was checked" />
            ) : (
              <ul className="space-y-2">
                {data.checked_not_affected.map((item) => (
                  <li key={`${item.entity_type}-${item.entity_id}`} className="rounded-xl border border-line bg-card p-4">
                    <p className="font-medium">
                      <span className="mr-1 text-ok" aria-hidden>
                        ✓
                      </span>
                      {names.label(item.entity_id, item.entity_type)}
                    </p>
                    <p className="mt-1 text-sm text-muted">{names.humanize(item.reason)}</p>
                    <details className="mt-1 text-xs text-muted">
                      <summary className="cursor-pointer">Details</summary>
                      <p className="mt-1">Original text: {item.reason}</p>
                      <p>ID: {item.entity_id}</p>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {data.unresolved_facts.length > 0 && (
            <section aria-labelledby="unsure" className="rounded-2xl border border-warn/30 bg-warn-bg p-4">
              <h2 id="unsure" className="text-lg font-semibold text-warn">
                Still unclear
              </h2>
              <ul className="mt-2 list-disc pl-5 text-sm">
                {data.unresolved_facts.map((f, i) => (
                  <li key={i}>{names.humanize(String(f.note ?? f.fact ?? f.detail ?? JSON.stringify(f)))}</li>
                ))}
              </ul>
            </section>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
            {d.status === 'analyzed' ? (
              <button className={btnPrimary} disabled={plans.isPending} onClick={() => plans.mutate()}>
                {plans.isPending ? 'Finding options…' : 'See recovery options'}
              </button>
            ) : (
              <Link to={`/disruptions/${id}/plans`} className={btnPrimary}>
                See recovery options
              </Link>
            )}
            <Link to={`/disruptions/${id}/log`} className="text-sm font-semibold text-brand underline">
              Activity log
            </Link>
          </div>
          {plans.error &&
            (plans.error instanceof ApiError && plans.error.isImpactUnclear ? (
              <PlanStateNotice state="impact_unclear" />
            ) : (
              <ErrorPanel error={plans.error} />
            ))}
        </>
      )}
    </div>
  )
}
