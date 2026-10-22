import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/errors'
import { approvePlan, discardPlanEdit, editPlan, getActivityLog, getExplanation, getPlan, rejectPlan, requestInfo, revalidatePlan } from '../api/endpoints'
import { AiBadge } from '../components/AiBadge'
import { CheckList } from '../components/CheckList'
import { PlanCost } from '../components/PlanCost'
import { PlanStatusBadge, StatusBadge } from '../components/StatusBadge'
import { ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary, btnSecondary, card, inputBase } from '../components/ui'
import { API_MODE } from '../config'
import { cn } from '../lib/cn'
import { actorName } from '../lib/activity'
import { formatDate, formatTimeOfDay, relativeTime } from '../lib/format'
import { describeAction, failingChecks, isDemoEdit, safeBenefits, stillToConfirm } from '../lib/plans'
import { useNames } from '../lib/useNames'
import { useSession } from '../state/session'
import { USERS, type RecoveryPlan } from '../types/contracts'

const STATUS_WORDS: Record<RecoveryPlan['status'], string> = {
  proposed: 'waiting for a decision',
  approved: 'approved',
  rejected: 'rejected',
  more_info_requested: 'waiting for more information',
  superseded: 'replaced by a newer version',
}

function supplierIds(plan: RecoveryPlan): string[] {
  const ids = plan.actions.map((a) => (a.parameters as Record<string, unknown>).supplier_id).filter((v): v is string => typeof v === 'string')
  return [...new Set(ids)]
}

export function PlanReview() {
  const { planId = '' } = useParams()
  const queryClient = useQueryClient()
  const names = useNames()
  const session = useSession()
  const user = USERS.find((u) => u.id === session.userId)!

  const planQuery = useQuery({ queryKey: ['plan', planId], queryFn: () => getPlan(planId) })
  const plan = planQuery.data
  const disruptionId = plan?.disruption_id
  const explanation = useQuery({
    queryKey: ['explanation', disruptionId],
    queryFn: () => getExplanation(disruptionId!),
    enabled: !!disruptionId,
  })

  const approvedLog = useQuery({
    queryKey: ['activity', disruptionId],
    queryFn: () => getActivityLog(disruptionId!),
    enabled: !!disruptionId && plan?.status === 'approved',
  })
  const [comment, setComment] = useState('')
  const [commentError, setCommentError] = useState<string | null>(null)
  const [mode, setMode] = useState<'idle' | 'confirm_open' | 'editing'>('idle')
  const [quantities, setQuantities] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState<string | null>(null)

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ['plan', planId] })
    void queryClient.invalidateQueries({ queryKey: ['plans'] })
    void queryClient.invalidateQueries({ queryKey: ['explanation'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['disruption'] })
    void queryClient.invalidateQueries({ queryKey: ['activity'] })
  }

  const body = () => ({ plan_version: plan!.version, comments: comment.trim() })
  const done = (message: string | null) => () => {
    setNotice(message)
    setMode('idle')
    setComment('')
    refresh()
  }

  const approve = useMutation({ mutationFn: () => approvePlan(planId, body()), onSuccess: done(null) })
  const reject = useMutation({ mutationFn: () => rejectPlan(planId, body()), onSuccess: done('Plan rejected.') })
  const askInfo = useMutation({
    mutationFn: () => requestInfo(planId, body()),
    onSuccess: done('More information requested (demo only: this is not saved to the server).'),
  })
  const edit = useMutation({
    mutationFn: () => {
      const actions = plan!.actions.map((a) => {
        const q = quantities[a.id]
        return q !== undefined && q !== '' ? { ...a, parameters: { ...(a.parameters as object), quantity: Number(q) } } : a
      })
      return editPlan(planId, { base_version: plan!.version, actions, assumptions: plan!.assumptions })
    },
    onSuccess: (result) => {
      queryClient.setQueryData(['plan', planId], result)
      setNotice(`Edited and re-checked (demo only). This is now version ${result.version}.`)
      setMode('idle')
      refresh()
    },
  })
  const discard = useMutation({
    mutationFn: () => discardPlanEdit(planId),
    onSuccess: (result) => {
      queryClient.setQueryData(['plan', planId], result)
      setNotice(`Demo edit discarded. Back to version ${result.version}.`)
      refresh()
    },
  })
  const recheck = useMutation({
    mutationFn: () => revalidatePlan(planId),
    onSuccess: (result) => {
      queryClient.setQueryData(['plan', planId], result)
      setNotice('Re-checked just now (demo only).')
      refresh()
    },
  })

  if (planQuery.isLoading) return <LoadingState label="Loading plan…" />
  if (planQuery.error) return <ErrorPanel error={planQuery.error} onRetry={() => void planQuery.refetch()} />
  if (!plan) return null

  const status = plan.validation?.status
  const failing = failingChecks(plan)
  const questions = stillToConfirm(plan)
  const comparison = explanation.data?.plan_comparisons.find((c) => c.plan_id === plan.id)
  // Not repeated if already shown as a failing check or an open question.
  const shown = new Set([...failing.map((c) => c.detail), ...questions])
  const watchOut = (comparison?.limitations ?? []).filter((l) => !shown.has(l))
  const editable = plan.actions.filter((a) => typeof (a.parameters as Record<string, unknown>).quantity === 'number')
  const suppliers = supplierIds(plan).map((id) => names.label(id, 'supplier'))

  const isOwner = user.role === 'owner'
  const mayAct = isOwner || session.staffCanTry
  const proposed = plan.status === 'proposed' || plan.status === 'more_info_requested'
  const demoEdit = isDemoEdit(plan)
  const busy = approve.isPending || reject.isPending || askInfo.isPending || edit.isPending || discard.isPending

  // Why the buttons are off (shown in words, never a silent disabled button).
  let blocked: string | null = null
  if (!proposed) blocked = `This plan is already ${STATUS_WORDS[plan.status]}.`
  else if (!mayAct) blocked = 'Only the business owner (Nurul) can decide on plans. You are signed in as Staff.'
  const approveBlocked =
    blocked ??
    (status === 'infeasible'
      ? `This plan won't work, so it can't be approved.${failing[0] ? ` ${names.humanize(failing[0].detail)}` : ''}`
      : null)

  const lastError = [approve, reject, askInfo, edit, recheck, discard].map((m) => m.error).find(Boolean)
  const staleError = lastError instanceof ApiError && lastError.isStale
  const benefits = safeBenefits(comparison?.benefits ?? [], plan, names.humanize)
  const approval = approvedLog.data?.items.find((e) => e.plan_id === plan.id && e.activity_type === 'plan_approved')
  const approver = approval ? actorName(approval.actor_id) : null

  function needComment(run: () => void) {
    if (!comment.trim()) {
      setCommentError('Please add a short comment first.')
      return
    }
    setCommentError(null)
    run()
  }


  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link to={`/disruptions/${plan.disruption_id}/plans`} className="text-sm font-semibold text-brand underline">
          ← All options
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {status && <StatusBadge status={status} />}
          <PlanStatusBadge status={plan.status} />
          {demoEdit && (
            <span className="rounded-full bg-warn-bg px-2.5 py-1 text-xs font-semibold text-warn">Version {plan.version}, edited (demo only)</span>
          )}
        </div>
        <h1 className="mt-2 text-3xl leading-tight font-semibold">{names.humanize(plan.summary)}</h1>
        <p className="mt-1 text-muted">
          Cost: <PlanCost plan={plan} />
        </p>
        {demoEdit && (
          <p className="mt-1 text-sm font-medium text-warn">
            Edited from the original plan (demo only): {editable.map((a) => names.humanize(describeAction(a, names, formatDate))).join('; ') || 'changed details'}
          </p>
        )}
      </div>

      {notice && (
        <p role="status" className="rounded-xl bg-ok-bg p-3 font-medium text-ok">
          {notice}
        </p>
      )}

      {plan.status === 'approved' && (
        <section className="rounded-2xl border border-ok/30 bg-ok-bg p-5" data-testid="approved-box">
          <p className="font-semibold text-ok">
            Approved{approver ? ` by ${approver}` : ''}
            {approval ? ` at ${formatTimeOfDay(approval.created_at)}` : ''}. Nothing has been sent. Next: prepare messages.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Link to={`/plans/${plan.id}/drafts`} className={btnPrimary}>
              Prepare messages
            </Link>
            <Link to={`/disruptions/${plan.disruption_id}/log`} className={btnSecondary}>
              View activity log
            </Link>
          </div>
        </section>
      )}

      {/* Follow-up after approving something that still has open questions. */}
      {plan.status === 'approved' && status === 'needs_confirmation' && (
        <section className="rounded-2xl border-2 border-warn/50 bg-warn-bg p-5" aria-labelledby="next-step">
          <h2 id="next-step" className="text-xl font-semibold text-warn">
            Next step: confirm with {suppliers.length ? suppliers.join(' and ') : 'the supplier'}
          </h2>
          <p className="mt-1 text-sm">You approved this plan, but these things are still unconfirmed. Check them before you rely on it:</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {(questions.length ? questions : ['Availability has not been confirmed.']).map((q) => (
              <li key={q}>{names.humanize(q)}</li>
            ))}
          </ul>
        </section>
      )}
      <section className={card} aria-labelledby="what">
        <h2 id="what" className="text-lg font-semibold">
          What this plan does
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {plan.actions.map((a) => (
            <li key={a.id}>{names.humanize(describeAction(a, names, formatDate))}</li>
          ))}
        </ul>
        {plan.assumptions.length > 0 && (
          <div className="mt-3">
            <p className="text-sm font-semibold">This assumes:</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
              {plan.assumptions.map((a) => (
                <li key={a}>{names.humanize(a)}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className={card} aria-labelledby="checks">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="checks" className="text-lg font-semibold">
            How it was checked
          </h2>
          {plan.validation?.validated_at && (
            <span className="text-xs text-muted">Checked {relativeTime(plan.validation.validated_at)}</span>
          )}
        </div>
        <div className="mt-3">
          {plan.validation ? <CheckList checks={plan.validation.checks} /> : <p className="text-sm text-muted">This plan has not been checked yet.</p>}
        </div>
        {status === 'needs_confirmation' && questions.length > 0 && (
          <div className="mt-4 rounded-xl bg-warn-bg p-3">
            <p className="text-sm font-semibold text-warn">Still to confirm</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
              {questions.map((q) => (
                <li key={q}>{names.humanize(q)}</li>
              ))}
            </ul>
          </div>
        )}
        <details className="mt-3 text-xs text-muted">
          <summary className="cursor-pointer">Details</summary>
          <p className="mt-1">
            Plan {plan.id}, version {plan.version}. Status code: {status ?? 'none'}. Created by: {plan.created_by}.
          </p>
        </details>
      </section>

      {comparison && (benefits.length > 0 || watchOut.length > 0) && (
        <section className={card} aria-labelledby="notes">
          <h2 id="notes" className="text-lg font-semibold">
            Good and not so good <AiBadge generatedBy={explanation.data?.generated_by} />
          </h2>
          {API_MODE !== 'real' && explanation.data?.generated_by === 'template' && (
            <p className="text-xs text-muted">Demo only: template text, because the AI explanation isn't built yet.</p>
          )}
          <div className={cn('mt-2 grid gap-4', benefits.length > 0 && watchOut.length > 0 && 'sm:grid-cols-2')}>
            {benefits.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {benefits.map((b) => (
                  <li key={b}>{names.humanize(b)}</li>
                ))}
              </ul>
            )}
            {watchOut.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {watchOut.map((b) => (
                  <li key={b}>{names.humanize(b)}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {/* ---- Decision ---- */}
      <section className={cn(card, 'space-y-4')} aria-labelledby="decide">
        <h2 id="decide" className="text-lg font-semibold">
          Your decision
        </h2>

        <p className="text-sm" data-testid="version-note">
          Approve applies to <strong>version {plan.version}</strong>
          {demoEdit ? ' (your demo edit)' : ''}.
        </p>
        {demoEdit && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl bg-warn-bg p-3 text-sm">
            <span>This version exists only in the demo. The server still has the original.</span>
            <button className={btnSecondary} disabled={busy || !proposed} onClick={() => discard.mutate()}>
              {discard.isPending ? 'Discarding…' : 'Discard demo edit (back to version 1)'}
            </button>
          </div>
        )}

        {!isOwner && !session.staffCanTry && (
          <p role="status" className="rounded-xl bg-info-bg p-3 font-semibold">
            Waiting for the owner's decision
          </p>
        )}

        <label className="block text-sm">
          <span className="font-semibold">Comment</span>{' '}
          <span className="text-muted">(needed to reject or to ask for more information)</span>
          <textarea
            value={comment}
            onChange={(e) => {
              setComment(e.target.value)
              setCommentError(null)
            }}
            rows={2}
            disabled={!proposed || !mayAct}
            className={cn(inputBase, 'mt-1', commentError ? 'border-bad' : 'border-line')}
          />
        </label>
        {commentError && (
          <p role="alert" className="-mt-2 text-sm font-medium text-bad">
            {commentError}
          </p>
        )}

        {mode === 'confirm_open' && (
          <div className="space-y-3 rounded-xl border-2 border-warn/50 bg-warn-bg p-4" role="group" aria-label="Approve with open questions">
            <p className="font-semibold text-warn">Approve with open questions?</p>
            <p className="text-sm">This plan is not fully confirmed yet. If you approve it, these stay open and you will need to confirm them with the supplier:</p>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {(questions.length ? questions : ['Availability has not been confirmed.']).map((q) => (
                <li key={q}>{names.humanize(q)}</li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-3">
              <button className={btnPrimary} disabled={busy} onClick={() => approve.mutate()}>
                {approve.isPending ? 'Approving…' : 'Approve with open questions'}
              </button>
              <button className={btnSecondary} onClick={() => setMode('idle')}>
                Go back
              </button>
            </div>
          </div>
        )}

        {mode === 'editing' && (
          <div className="space-y-3 rounded-xl border border-line bg-paper p-4">
            <p className="font-semibold">
              Edit this plan <span className="rounded-full bg-warn-bg px-2 py-0.5 text-xs text-warn">Demo only</span>
            </p>
            <p className="text-xs text-muted">
              Editing isn't built on the backend yet. Saving creates a new version and re-checks it with scripted demo rules (for example, 20 → 10 chairs).
            </p>
            {editable.map((a) => (
              <label key={a.id} className="block text-sm">
                <span className="font-semibold">{names.humanize(describeAction(a, names, formatDate))}</span>
                <span className="mt-1 block text-muted">Quantity</span>
                <input
                  type="number"
                  min={1}
                  className={cn(inputBase, 'max-w-32 border-line')}
                  value={quantities[a.id] ?? String((a.parameters as Record<string, unknown>).quantity)}
                  onChange={(e) => setQuantities((q) => ({ ...q, [a.id]: e.target.value }))}
                />
              </label>
            ))}
            {editable.length === 0 && <p className="text-sm text-muted">This plan has no quantity to change.</p>}
            <div className="flex flex-wrap gap-3">
              <button className={btnPrimary} disabled={busy || editable.length === 0} onClick={() => edit.mutate()}>
                {edit.isPending ? 'Saving…' : 'Save and re-check'}
              </button>
              <button className={btnSecondary} onClick={() => setMode('idle')}>
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            className={btnPrimary}
            disabled={!!approveBlocked || busy}
            onClick={() => (status === 'needs_confirmation' ? setMode('confirm_open') : approve.mutate())}
          >
            {approve.isPending && mode !== 'confirm_open' ? 'Approving…' : status === 'needs_confirmation' ? 'Approve with open questions…' : 'Approve plan'}
          </button>
          <button className={btnSecondary} disabled={!!blocked || busy} onClick={() => setMode('editing')}>
            Edit
          </button>
          <button className={btnSecondary} disabled={!!blocked || busy} onClick={() => needComment(() => reject.mutate())}>
            Reject
          </button>
          <button className={btnSecondary} disabled={!!blocked || busy} onClick={() => needComment(() => askInfo.mutate())}>
            Request info
          </button>
        </div>

        {approveBlocked && (
          <p className="text-sm font-medium text-muted" data-testid="blocked-reason">
            {approveBlocked}
          </p>
        )}

        {proposed && mayAct && (
          <button className="text-sm font-semibold text-brand underline" disabled={recheck.isPending} onClick={() => recheck.mutate()}>
            {recheck.isPending ? 'Re-checking…' : 'Re-check this plan (demo only)'}
          </button>
        )}

        {lastError && (
          <div className="space-y-2">
            <ErrorPanel error={lastError} />
            {staleError && (
              <button
                className={btnSecondary}
                onClick={() => {
                  [approve, reject, askInfo, edit, recheck, discard].forEach((m) => m.reset())
                  refresh()
                }}
              >
                Reload the latest version
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
