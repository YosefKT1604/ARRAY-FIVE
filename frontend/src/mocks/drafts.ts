// MOCK-ONLY stand-in for POST /recovery-plans/{id}/drafts (Person 5's draft_messages).
// Template messages with [PLACEHOLDER] fields the owner must fill in. Nothing is ever sent.
import { formatDate } from '../lib/format'
import type { DraftMessage, RecoveryPlan } from '../types/contracts'
import { fixtures } from './db'

type Params = Record<string, unknown>

const longDate = (d: string) => `${formatDate(d)} 2026`

export function buildDrafts(plan: RecoveryPlan): Omit<DraftMessage, 'id'>[] {
  const drafts: Omit<DraftMessage, 'id'>[] = []
  for (const action of plan.actions) {
    const p = action.parameters as Params
    const supplier = fixtures.seed.suppliers.find((s) => s.id === p.supplier_id)
    if (!supplier) continue
    const resource = fixtures.seed.resources.find((r) => r.id === p.resource_id)
    let body: string
    let placeholders: string[]
    if (action.action_type === 'source_alternative_supplier') {
      const date = typeof p.expected_arrival_date === 'string' ? longDate(p.expected_arrival_date) : '[DELIVERY_DATE]'
      body = `Hi ${supplier.name}, we would like to rent ${p.quantity} ${resource?.name.toLowerCase() ?? 'items'} for delivery on ${date} to [DELIVERY_ADDRESS]. Please confirm they are available and the total price. Thank you, [YOUR_NAME]`
      placeholders = ['DELIVERY_ADDRESS', 'YOUR_NAME']
    } else if (action.action_type === 'contact_supplier') {
      const request = String(p.request ?? 'could you help with our order')
      body = `Hi ${supplier.name}, ${request.charAt(0).toLowerCase()}${request.slice(1)}. Can you confirm whether this is possible, and any extra charge? Please reply by [REPLY_BY_TIME]. Thank you, [YOUR_NAME]`
      placeholders = ['REPLY_BY_TIME', 'YOUR_NAME']
    } else {
      continue
    }
    drafts.push({
      plan_id: plan.id,
      recipient_type: 'supplier',
      recipient_id: supplier.id,
      body,
      placeholders,
      status: 'draft',
      generated_by: 'template',
    })
  }
  return drafts
}
