import type { ReactNode } from 'react'
import { ApiError } from '../api/errors'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 rounded-xl border border-line bg-card p-5 text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-line border-t-brand" aria-hidden />
      {label}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-card p-6 text-center">
      <p className="font-display text-lg">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  )
}

/** Plain-words error with the technical bits tucked into "Details". */
export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : undefined
  const message = api ? api.userMessage : 'Something unexpected went wrong.'
  return (
    <div role="alert" className="rounded-xl border border-bad/30 bg-bad-bg p-5 text-bad">
      <p className="font-semibold">{message}</p>
      <details className="mt-2 text-sm text-ink">
        <summary className="cursor-pointer text-muted">Details</summary>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          {api ? (
            <>
              <dt className="text-muted">Status</dt>
              <dd>{api.status || 'no response'}</dd>
              <dt className="text-muted">Code</dt>
              <dd>{api.code ?? 'none sent'}</dd>
              <dt className="text-muted">Backend said</dt>
              <dd>{api.detail}</dd>
              {api.requestId && (
                <>
                  <dt className="text-muted">Request</dt>
                  <dd>{api.requestId}</dd>
                </>
              )}
            </>
          ) : (
            <>
              <dt className="text-muted">Error</dt>
              <dd>{String(error)}</dd>
            </>
          )}
        </dl>
      </details>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg border border-bad/40 bg-card px-3 py-1.5 text-sm font-medium text-bad hover:bg-white"
        >
          Try again
        </button>
      )}
    </div>
  )
}
