import { describe, expect, it } from 'vitest'
import { describeActivity } from '../lib/activity'
import { splitPlaceholders } from '../lib/drafts'
import { safeBenefits, stillToConfirm } from '../lib/plans'
import { mockEdit } from '../mocks/edit'
import { fixtures } from '../mocks/db'
import type { ActivityLogEntry } from '../types/contracts'

const [, delima, cahaya] = fixtures.plans

describe('plan card wording rules', () => {
  it('drops a benefit that is the reason a check fails (Delima arrives 23 Oct)', () => {
    const out = safeBenefits(['Cheapest option (RM 56.00).', 'Arrives Fri 23 Oct.'], delima, (t) => t.replace('2026-10-23', 'Fri 23 Oct'))
    expect(out).toEqual(['Cheapest option (RM 56.00).'])
  })

  it('lists each open question once', () => {
    const dup = { ...cahaya, assumptions: [cahaya.assumptions[0], cahaya.assumptions[0]] }
    const q = stillToConfirm(dup)
    expect(new Set(q).size).toBe(q.length)
    expect(q.length).toBeGreaterThan(0)
  })
})

describe('demo edit', () => {
  it('changes the title with the quantity (20 -> 10)', () => {
    const base = fixtures.plans[0]
    const actions = base.actions.map((a) => ({ ...a, parameters: { ...(a.parameters as object), quantity: 10 } }))
    const edited = mockEdit(base, { base_version: 1, actions, assumptions: [] })
    expect(edited.summary).toContain('10 chairs')
    expect(edited.summary).not.toContain('20')
  })
})

describe('activity log sentences', () => {
  const entry = (over: Partial<ActivityLogEntry>): ActivityLogEntry => ({
    id: 'LOG-1', disruption_id: 'D-001', plan_id: 'RP-001', actor_id: 'U-01', activity_type: 'plan_approved', details: {}, created_at: '2026-10-20T03:00:00Z', ...over,
  })
  const ctx = { planTitle: () => 'Rent 20 chairs from Cahaya.', humanize: (t: string) => t }

  it('names who approved what', () => {
    expect(describeActivity(entry({}), ctx)).toBe('Nurul approved ‘Rent 20 chairs from Cahaya’.')
  })
  it('explains a denied attempt', () => {
    expect(describeActivity(entry({ actor_id: 'U-02', activity_type: 'approval_denied' }), ctx)).toContain("Hafiz tried to approve or reject")
  })
})

describe('draft placeholders', () => {
  it('splits out [PLACEHOLDER] fields', () => {
    const parts = splitPlaceholders('Hi [NAME], thanks')
    expect(parts.map((p) => p.placeholder)).toEqual([false, true, false])
  })
})

describe('activity log versions', () => {
  it('says which version was approved', () => {
    const e: ActivityLogEntry = { id: 'LOG-2', disruption_id: 'D-001', plan_id: 'RP-001', actor_id: 'U-01', activity_type: 'plan_approved', details: { plan_version: 1 }, created_at: '2026-10-20T03:00:00Z' }
    expect(describeActivity(e, { planTitle: () => 'Rent 20 chairs.', humanize: (t) => t })).toBe('Nurul approved version 1 of ‘Rent 20 chairs’.')
  })
})
