import { describe, expect, it } from 'vitest'
import { dropRepeatedIds } from '../lib/useNames'

const NAMES: Record<string, string> = {
  'S-01': 'Maju Rental Supplies',
  'J-02': 'Tekno Solutions product seminar',
  'CM-02': 'Tekno Solutions product seminar', // a commitment stands for its event's name
}
const nameOf = (id: string) => NAMES[id]

describe('dropRepeatedIds', () => {
  it('drops an ID in brackets right after its own name', () => {
    expect(dropRepeatedIds('Maju Rental Supplies (S-01) will deliver late.', nameOf)).toBe(
      'Maju Rental Supplies will deliver late.',
    )
  })
  it("drops a commitment's ID when its event is already named in the clause", () => {
    expect(dropRepeatedIds('Tekno Solutions product seminar (J-02) customer commitment (CM-02)', nameOf)).toBe(
      'Tekno Solutions product seminar customer commitment',
    )
  })
  it('keeps the ID when the name is not there, or only in an earlier sentence', () => {
    expect(dropRepeatedIds('The supplier (S-01) is late.', nameOf)).toBe('The supplier (S-01) is late.')
    expect(dropRepeatedIds('Maju Rental Supplies is late. A second note (S-01).', nameOf)).toBe(
      'Maju Rental Supplies is late. A second note (S-01).',
    )
  })
  it('keeps unknown IDs and bare IDs', () => {
    expect(dropRepeatedIds('Plan (RP-001) and S-01 stay.', nameOf)).toBe('Plan (RP-001) and S-01 stay.')
  })
})
