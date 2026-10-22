// MOCK-ONLY stand-in for POST /disruptions/extract (Person 5 builds the real one).
// Deterministic keyword rules over the seed aliases. It prefills the form and never decides anything.
import type { ExtractionResult, UnresolvedField } from '../types/contracts'
import { fixtures } from './db'

const MATERIAL = ['supplier_id', 'resource_id', 'quantity_affected', 'new_arrival_date'] as const

const DATE_WORDS: Record<string, string> = { friday: '2026-10-23', jumaat: '2026-10-23', tomorrow: '2026-10-21', esok: '2026-10-21' }

export function mockExtract(message: string): ExtractionResult {
  const text = message.toLowerCase()
  const evidence: Record<string, string> = {}
  const unresolved: UnresolvedField[] = []

  // The demo WhatsApp message never names the supplier (it arrives from Maju's number), and the
  // contract's extract request carries only the text. So the mock recognises the fixture message itself.
  const isDemoMessage = message.trim() === fixtures.incident.supplier_message.text
  const supplier = fixtures.seed.suppliers.find(
    (s) =>
      (isDemoMessage && s.id === fixtures.incident.form_input.supplier_id) ||
      [s.name, ...s.aliases].some((a) => text.includes(a.toLowerCase())),
  )
  const resource = fixtures.seed.resources.find((r) => [r.name, ...r.aliases].some((a) => text.includes(a.toLowerCase())))
  const qty = /\b(\d{1,4})\b/.exec(message)
  const dateWord = Object.keys(DATE_WORDS).find((w) => text.includes(w))
  const delivery = fixtures.seed.deliveries.find(
    (d) => d.supplier_id === supplier?.id && d.resource_id === resource?.id,
  )

  if (supplier) evidence.supplier_id = isDemoMessage ? `${supplier.name} (the sender)` : supplier.name
  if (resource) evidence.resource_id = resource.name
  if (qty) evidence.quantity_affected = qty[0]
  if (dateWord) evidence.new_arrival_date = dateWord

  const miss = (field: string, note: string) =>
    unresolved.push({ field, reason: 'missing', raw_value: null, candidates: [], note })
  if (!supplier) miss('supplier_id', 'We could not tell which supplier this is from.')
  if (!resource) miss('resource_id', 'We could not tell what item is affected.')
  if (!qty) miss('quantity_affected', 'No quantity found in the message.')
  if (!dateWord) miss('new_arrival_date', 'No new arrival date found in the message.')

  const mainDemo = supplier?.id === 'S-01' && resource?.id === 'R-01' && qty?.[0] === '20' && dateWord === 'friday'
  const base = fixtures.incident.expected_normalized_incident

  return {
    schema_version: '1.0',
    draft_incident: {
      schema_version: '1.0',
      type: 'supplier_delay',
      source: 'message',
      supplier_id: supplier?.id ?? null,
      resource_id: resource?.id ?? null,
      delivery_id: delivery?.id ?? null,
      quantity_affected: qty ? Number(qty[0]) : null,
      original_arrival_date: delivery?.expected_date ?? null,
      new_arrival_date: dateWord ? DATE_WORDS[dateWord] : null,
      description: mainDemo ? base.description : message.trim(),
      unresolved_fields: unresolved,
    } as ExtractionResult['draft_incident'],
    field_evidence: evidence,
    unresolved_fields: unresolved,
    needs_clarification: unresolved.some((u) => (MATERIAL as readonly string[]).includes(u.field)),
    clarification_questions: unresolved.map((u) => u.note ?? `Please fill in ${u.field}.`),
    generated_by: 'template',
    fallback_used: true,
    warnings: ['Mock: message reading is simulated with simple keyword rules.'],
  }
}
