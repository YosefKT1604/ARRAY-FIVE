import type { ErrorCode } from '../types/contracts'

export class ApiError extends Error {
  constructor(
    public status: number,
    /** Machine code. The real backend sends none, so it is inferred when possible. */
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
      case 'UNAUTHENTICATED':
        return 'Please pick who you are (top right) and try again.'
      case 'NOT_FOUND':
        return "We couldn't find that. The demo may have been reset."
      case 'DUPLICATE_DISRUPTION':
        return 'This problem has already been reported.'
      case 'STALE_PLAN_VERSION':
        return 'This plan changed since you opened it. Reload to see the latest version.'
      case 'PLAN_ALREADY_DECIDED':
        return 'Someone has already decided on this plan. Reload to see what was decided.'
      case 'PLAN_INFEASIBLE':
        return "This plan won't work, so it can't be approved."
      case 'VALIDATION_ERROR':
        return 'Some details need fixing. Check the highlighted fields.'
      case 'INTERNAL_ERROR':
        return 'Something went wrong on our side. Please try again.'
    }
    if (this.status === 0) return "Can't reach the server. Check that the backend is running, or switch to mock mode."
    if (this.status >= 500) return 'Something went wrong on our side. Please try again.'
    // 409 (or anything else) with no recognisable code: show the backend's own words.
    return this.detail ? (/[.!?]$/.test(this.detail) ? this.detail : `${this.detail}.`) : 'That action could not be completed.'
  }
}

/** Contract section 8 uses `code`; the real backend sends none, so read the detail text. */
function inferCode(status: number, detail: string): ErrorCode | undefined {
  const d = detail.toLowerCase()
  switch (status) {
    case 400:
      return 'BAD_REQUEST'
    case 401:
      return 'UNAUTHENTICATED'
    case 403:
      return 'FORBIDDEN'
    case 404:
      return 'NOT_FOUND'
    case 422:
      return 'VALIDATION_ERROR'
    case 409:
      if (d.includes('duplicate')) return 'DUPLICATE_DISRUPTION'
      if (d.includes('infeasible')) return 'PLAN_INFEASIBLE'
      if (/is at version|stale/.test(d)) return 'STALE_PLAN_VERSION'
      if (/already (approved|rejected|decided|superseded)|is already/.test(d)) return 'PLAN_ALREADY_DECIDED'
      if (/needs clarification|analyzed/.test(d)) return 'INVALID_STATE_TRANSITION'
      return undefined
    default:
      return status >= 500 ? 'INTERNAL_ERROR' : undefined
  }
}

type Json = Record<string, unknown>

/** Accepts both shapes: contract section 8 `{error:{...}}` and RFC 9457 Problem Details. */
export function parseErrorBody(status: number, body: unknown): ApiError {
  const b = (body && typeof body === 'object' ? body : {}) as Json
  const fieldErrors: Record<string, string> = {}

  if (b.error && typeof b.error === 'object') {
    const e = b.error as Json
    const details = Array.isArray(e.details) ? (e.details as Json[]) : []
    for (const d of details) if (typeof d.field === 'string') fieldErrors[d.field] = String(d.issue ?? '')
    const message = String(e.message ?? 'Request failed')
    const code = (typeof e.code === 'string' ? e.code : inferCode(status, message)) as ErrorCode | undefined
    return new ApiError(status, code, message, fieldErrors, typeof e.request_id === 'string' ? e.request_id : undefined)
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
  const code = (typeof b.code === 'string' ? b.code : inferCode(status, detail)) as ErrorCode | undefined
  return new ApiError(status, code, detail, fieldErrors)
}
