import type { ErrorCode } from '../types/contracts'

export class ApiError extends Error {
  constructor(
    public status: number,
    /** Machine code from the backend's `code` field (CONTRACTS.md section 8). */
    public code: ErrorCode | undefined,
    /** The backend's own text (Problem Details `detail` or contract `message`). */
    public detail: string,
    /** field name -> message, from 422 responses */
    public fieldErrors: Record<string, string> = {},
    public requestId?: string,
  ) {
    super(detail)
  }

  /** Plain-words message for non-technical readers. */
  get userMessage(): string {
    switch (this.code) {
      case 'FORBIDDEN':
        return 'Only the business owner can approve or reject plans. Switch to the owner and try again.'
      case 'UNAUTHORIZED':
        return 'Please pick who you are (top right) and try again.'
      case 'NOT_FOUND':
        return "We couldn't find that. The demo may have been reset."
      case 'DUPLICATE_DISRUPTION':
        return 'This problem has already been reported.'
      case 'STALE_PLAN_VERSION':
        return 'This plan changed since you opened it. Reload to see the latest version.'
      case 'PLAN_INFEASIBLE':
        return "This plan won't work, so it can't be approved."
      case 'VALIDATION_ERROR':
        return 'Some details need fixing. Check the highlighted fields.'
      case 'INTERNAL_ERROR':
        return 'Something went wrong on our side. Please try again.'
      case 'INVALID_STATE_TRANSITION': {
        // One code covers several cases; the backend's text says which, so use its own words.
        const done = /is already (\w+)/i.exec(this.detail)
        if (done) return `Someone has already ${done[1] === 'more_info_requested' ? 'asked for more information on' : done[1]} this plan. Reload to see what happened.`
        return this.sentence()
      }
    }
    if (this.status === 0) return "Can't reach the server. Check that the backend is running, or switch to mock mode."
    if (this.status >= 500) return 'Something went wrong on our side. Please try again.'
    // Anything without a code we know: show the backend's own words.
    return this.sentence()
  }

  /** Should the UI offer "Reload the latest version"? */
  get isStale(): boolean {
    return this.code === 'STALE_PLAN_VERSION' || this.code === 'INVALID_STATE_TRANSITION'
  }

  private sentence(): string {
    if (!this.detail) return 'That action could not be completed.'
    return /[.!?]$/.test(this.detail) ? this.detail : `${this.detail}.`
  }
}

/** Only used when the response carries no `code` (e.g. a proxy error): derive it from the status. */
function codeFromStatus(status: number): ErrorCode | undefined {
  switch (status) {
    case 400:
      return 'BAD_REQUEST'
    case 401:
      return 'UNAUTHORIZED'
    case 403:
      return 'FORBIDDEN'
    case 404:
      return 'NOT_FOUND'
    case 422:
      return 'VALIDATION_ERROR'
    default:
      return status >= 500 ? 'INTERNAL_ERROR' : undefined
  }
}

type Json = Record<string, unknown>

/**
 * Accepts both shapes: contract section 8 `{error:{code,...}}` and the backend's RFC 9457
 * Problem Details with an added `code` field. The `code` the backend sends always wins.
 */
export function parseErrorBody(status: number, body: unknown): ApiError {
  const b = (body && typeof body === 'object' ? body : {}) as Json
  const fieldErrors: Record<string, string> = {}

  if (b.error && typeof b.error === 'object') {
    const e = b.error as Json
    const details = Array.isArray(e.details) ? (e.details as Json[]) : []
    for (const d of details) if (typeof d.field === 'string') fieldErrors[d.field] = String(d.issue ?? '')
    const code = (typeof e.code === 'string' ? e.code : codeFromStatus(status)) as ErrorCode | undefined
    return new ApiError(status, code, String(e.message ?? 'Request failed'), fieldErrors, typeof e.request_id === 'string' ? e.request_id : undefined)
  }

  const errors = Array.isArray(b.errors) ? (b.errors as Json[]) : Array.isArray(b.detail) ? (b.detail as Json[]) : []
  for (const e of errors) {
    const loc = Array.isArray(e.loc) ? (e.loc as unknown[]) : []
    const field = loc
      .filter((p) => p !== 'body')
      .map(String)
      .pop()
    if (field) fieldErrors[field] = String(e.msg ?? '')
  }
  const detail = typeof b.detail === 'string' ? b.detail : typeof b.title === 'string' ? b.title : 'Request failed'
  const code = (typeof b.code === 'string' ? b.code : codeFromStatus(status)) as ErrorCode | undefined
  return new ApiError(status, code, detail, fieldErrors)
}
