import { describe, expect, it } from 'vitest'
import plansFixture from '../../../fixtures/demo/expected_plans.json'
import { mockEdit, MOCK_CANNOT_VALIDATE } from '../mocks/edit'
import { checkLabel, sortByRank, stillToConfirm } from '../lib/plans'
import type { PlanEditRequest, RecoveryAction, RecoveryPlan } from '../types/contracts'

const plans = plansFixture.plans as unknown as RecoveryPlan[]

const withQuantity = (plan: RecoveryPlan, quantity: number): PlanEditRequest => ({
  base_version: plan.version,
  actions: plan.actions.map((a): RecoveryAction => ({ ...a, parameters: { ...(a.parameters as object), quantity } })),
  assumptions: plan.assumptions,
})

describe('mock plan edit (scripted demo only)', () => {
  it('replays the fixture edit: 20 -> 10 chairs is infeasible, QUANTITY_SUFFICIENT fails, short 10', () => {
    const v2 = mockEdit(plans[0], withQuantity(plans[0], 10))
    expect(v2.version).toBe(2)
    expect(v2.validation?.status).toBe('infeasible')
    const failed = v2.validation?.checks.filter((c) => c.result === 'fail')
    expect(failed?.map((c) => c.code)).toEqual(['QUANTITY_SUFFICIENT'])
    expect(failed?.[0].detail).toContain('short 10')
    expect(v2.estimated_cost).toBeNull()
    expect(v2.rank).toBeNull()
  })

  it('returns needs_confirmation for any other edit, never a guess', () => {
    const v2 = mockEdit(plans[0], withQuantity(plans[0], 15))
    expect(v2.validation?.status).toBe('needs_confirmation')
    expect(v2.validation?.unresolved_assumptions).toContain(MOCK_CANNOT_VALIDATE)
  })
})

describe('plan helpers', () => {
  it('sorts by the API rank and puts unranked plans last', () => {
    const ordered = sortByRank([plans[1], plans[2], plans[0]])
    expect(ordered[0].id).toBe('RP-001')
    expect(ordered[0].rank).toBe(1)
  })

  it('collects open questions from assumptions and unresolved checks', () => {
    const questions = stillToConfirm(plans[2])
    expect(questions.length).toBeGreaterThan(0)
    expect(new Set(questions).size).toBe(questions.length)
  })

  it('words failing checks in the negative', () => {
    expect(checkLabel('DEADLINE_MET', 'fail')).toBe('Arrives too late')
    expect(checkLabel('DEADLINE_MET', 'pass')).toBe('Arrives in time')
  })
})
