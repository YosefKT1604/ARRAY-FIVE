import { describe, expect, it } from 'vitest'
import { formatDate, formatDateTime, formatMoney } from '../lib/format'

describe('formatMoney', () => {
  it('formats MYR as RM', () => {
    expect(formatMoney({ amount: '80.00', currency: 'MYR' })).toBe('RM 80.00')
  })
  it('never shows RM 0.00 for unknown cost', () => {
    expect(formatMoney(null)).toBe('Cost unknown')
    expect(formatMoney(undefined)).toBe('Cost unknown')
  })
  it('keeps a genuine zero as zero', () => {
    expect(formatMoney({ amount: '0.00', currency: 'MYR' })).toBe('RM 0.00')
  })
})

describe('dates in Asia/Kuala_Lumpur', () => {
  it('does not shift calendar dates', () => {
    expect(formatDate('2026-10-22')).toContain('22')
    expect(formatDate('2026-10-22')).toContain('Oct')
  })
  it('converts an offset-less (UTC) timestamp to KL time', () => {
    // 16:30 UTC is 00:30 next day in KL
    expect(formatDateTime('2026-10-21T16:30:00')).toContain('22')
  })
})
