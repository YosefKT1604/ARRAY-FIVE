import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { approveDraft, createDrafts, getPlan } from '../api/endpoints'
import { AiBadge } from '../components/AiBadge'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary, card } from '../components/ui'
import { API_MODE } from '../config'
import { splitPlaceholders } from '../lib/drafts'
import { useNames } from '../lib/useNames'
import { useSession } from '../state/session'
import { USERS, type DraftMessage } from '../types/contracts'

function DraftCard({ draft, canApprove }: { draft: DraftMessage; canApprove: boolean }) {
  const names = useNames()
  const queryClient = useQueryClient()
  const approve = useMutation({
    mutationFn: () => approveDraft(draft.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['drafts'] }),
  })
  const recipient = draft.recipient_type === 'supplier' ? names.label(draft.recipient_id, 'supplier') : draft.recipient_id
  const approved = draft.status === 'approved'

  return (
    <li className={card} data-testid="draft-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">To: {recipient}</p>
        <span className="flex items-center gap-2">
          <AiBadge generatedBy={draft.generated_by} />
          <span className="rounded-full bg-warn-bg px-2.5 py-1 text-xs font-semibold text-warn">Draft — not sent</span>
        </span>
      </div>
      <p className="mt-3 rounded-xl bg-paper p-3 leading-relaxed whitespace-pre-wrap">
        {splitPlaceholders(draft.body).map((part, i) =>
          part.placeholder ? (
            <mark key={i} className="rounded bg-warn-bg px-1 font-semibold text-warn" title="Fill this in before using the message">
              {part.text}
            </mark>
          ) : (
            <span key={i}>{part.text}</span>
          ),
        )}
      </p>
      {draft.placeholders.length > 0 && !approved && (
        <p className="mt-2 text-sm text-muted">Fill in the highlighted fields: {draft.placeholders.join(', ')}.</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {approved ? (
          <p className="font-semibold text-ok">Draft approved. Still not sent: copy it into your own chat or email.</p>
        ) : (
          <button className={btnPrimary} disabled={!canApprove || approve.isPending} onClick={() => approve.mutate()}>
            {approve.isPending ? 'Approving…' : 'Approve draft'}
          </button>
        )}
        {!canApprove && !approved && <span className="text-sm text-muted">Only the owner can approve drafts.</span>}
      </div>
      {approve.error && <div className="mt-2"><ErrorPanel error={approve.error} /></div>}
    </li>
  )
}

export function Drafts() {
  const { planId = '' } = useParams()
  const session = useSession()
  const canApprove = USERS.find((u) => u.id === session.userId)?.role === 'owner'

  const plan = useQuery({ queryKey: ['plan', planId], queryFn: () => getPlan(planId) })
  const drafts = useQuery({
    queryKey: ['drafts', planId],
    queryFn: () => createDrafts(planId),
    enabled: plan.data?.status === 'approved',
  })

  if (plan.isLoading) return <LoadingState label="Loading…" />
  if (plan.error) return <ErrorPanel error={plan.error} onRetry={() => void plan.refetch()} />

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link to={`/plans/${planId}`} className="text-sm font-semibold text-brand underline">
          ← Back to the plan
        </Link>
        <h1 className="mt-2 text-3xl font-semibold">Draft messages</h1>
        <p className="mt-1 text-muted">
          Nothing is sent from this app. Check each message, fill in the highlighted fields, then send it yourself.
        </p>
        {API_MODE !== 'real' && <p className="mt-1 text-xs text-muted">Demo only: template text, because drafting isn't built yet.</p>}
      </div>

      {plan.data && plan.data.status !== 'approved' ? (
        <EmptyState title="Approve a plan first">Messages are prepared once a plan has been approved.</EmptyState>
      ) : drafts.isLoading ? (
        <LoadingState label="Preparing drafts…" />
      ) : drafts.error ? (
        <ErrorPanel error={drafts.error} onRetry={() => void drafts.refetch()} />
      ) : drafts.data?.items.length === 0 ? (
        <EmptyState title="No messages needed">This plan has no steps that need a message.</EmptyState>
      ) : (
        <ul className="space-y-4">
          {drafts.data?.items.map((d) => (
            <DraftCard key={d.id} draft={d} canApprove={canApprove} />
          ))}
        </ul>
      )}
    </div>
  )
}
