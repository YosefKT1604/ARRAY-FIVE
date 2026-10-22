import { describe, expect, it } from 'vitest'
import incident from '../../../fixtures/demo/incident.json'
import { mockExtract } from '../mocks/extract'

describe('mock message extraction (prefill only)', () => {
  it('reads the demo message into the fixture incident', () => {
    const r = mockExtract(incident.supplier_message.text, incident.supplier_message.from_contact)
    expect(r.needs_clarification).toBe(false)
    expect(r.draft_incident).toMatchObject({
      supplier_id: 'S-01',
      resource_id: 'R-01',
      delivery_id: 'DL-01',
      quantity_affected: 20,
      new_arrival_date: '2026-10-23',
    })
  })

  it('flags what it cannot find instead of guessing', () => {
    const r = mockExtract('Boss, delivery will be late sorry')
    expect(r.needs_clarification).toBe(true)
    expect(r.unresolved_fields.map((u) => u.field)).toEqual(
      expect.arrayContaining(['supplier_id', 'resource_id', 'quantity_affected', 'new_arrival_date']),
    )
    expect(r.draft_incident.supplier_id).toBeNull()
  })
})
