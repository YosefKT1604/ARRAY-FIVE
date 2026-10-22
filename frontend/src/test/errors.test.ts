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

  it('reads the real backend Problem Details shape and maps 422 fields', () => {
    const e = parseErrorBody(422, {
      title: 'Unprocessable Entity',
      status: 422,
      detail: 'Validation failed',
      errors: [{ loc: ['body', 'quantity_affected'], msg: 'must be >= 1', type: 'x' }],
    })
    expect(e.code).toBe('VALIDATION_ERROR')
    expect(e.fieldErrors).toEqual({ quantity_affected: 'must be >= 1' })
  })

  it('infers codes from the backend detail text when none is sent', () => {
    expect(parseErrorBody(409, { detail: 'Plan RP-001 is at version 2, not 1' }).code).toBe('STALE_PLAN_VERSION')
    expect(parseErrorBody(409, { detail: 'Plan RP-002 is infeasible and cannot be approved' }).code).toBe(
      'PLAN_INFEASIBLE',
    )
    expect(parseErrorBody(403, { detail: 'U-02 (staff) may not approve or reject plans' }).code).toBe('FORBIDDEN')
  })

  it('recognises an already-decided plan', () => {
    const e = parseErrorBody(409, { detail: 'Plan RP-001 is already approved' })
    expect(e.code).toBe('PLAN_ALREADY_DECIDED')
    expect(e.userMessage).toMatch(/already decided/)
  })

  it('shows the backend text in plain words when a 409 code cannot be inferred', () => {
    const e = parseErrorBody(409, { detail: 'Something odd happened with the order' })
    expect(e.code).toBeUndefined()
    expect(e.userMessage).toBe('Something odd happened with the order.')
  })
})
