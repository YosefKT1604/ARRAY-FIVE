import { describe, expect, it } from 'vitest'
import { parseErrorBody } from '../api/errors'

describe('parseErrorBody', () => {
  it('reads the contract section 8 shape', () => {
    const e = parseErrorBody(409, {
      error: { code: 'DUPLICATE_DISRUPTION', message: 'Already open', details: [], request_id: 'req-1' },
    })
    expect(e.code).toBe('DUPLICATE_DISRUPTION')
    expect(e.requestId).toBe('req-1')
  })

  it('uses the code field the real backend sends (Problem Details + code)', () => {
    const e = parseErrorBody(409, {
      title: 'Conflict',
      status: 409,
      detail: 'Plan RP-001 is at version 2, not 1',
      code: 'STALE_PLAN_VERSION',
    })
    expect(e.code).toBe('STALE_PLAN_VERSION')
    expect(e.isStale).toBe(true)
  })

  it('maps 422 field errors', () => {
    const e = parseErrorBody(422, {
      title: 'Unprocessable Content',
      status: 422,
      detail: 'Validation failed',
      code: 'VALIDATION_ERROR',
      errors: [{ loc: ['body', 'quantity_affected'], msg: 'must be >= 1', type: 'x' }],
    })
    expect(e.fieldErrors).toEqual({ quantity_affected: 'must be >= 1' })
  })

  it('does not guess codes from detail text; a 409 without a code shows the backend words', () => {
    const e = parseErrorBody(409, { detail: 'Something odd happened with the order' })
    expect(e.code).toBeUndefined()
    expect(e.userMessage).toBe('Something odd happened with the order.')
  })

  it('explains INVALID_STATE_TRANSITION for an already-decided plan in plain words', () => {
    const e = parseErrorBody(409, { detail: 'Plan RP-001 is already approved', code: 'INVALID_STATE_TRANSITION' })
    expect(e.userMessage).toBe('Someone has already approved this plan. Reload to see what happened.')
  })

  it('shows the backend text for other INVALID_STATE_TRANSITION cases', () => {
    const e = parseErrorBody(409, {
      detail: 'Disruption needs clarification before it can be analyzed',
      code: 'INVALID_STATE_TRANSITION',
    })
    expect(e.userMessage).toBe('Disruption needs clarification before it can be analyzed.')
  })

  it('falls back to the HTTP status when no code is sent', () => {
    expect(parseErrorBody(403, { detail: 'nope' }).code).toBe('FORBIDDEN')
    expect(parseErrorBody(401, { detail: 'nope' }).code).toBe('UNAUTHORIZED')
  })
})
