// MOCK-ONLY stand-in for P5's WhatsApp inbox (POST /whatsapp/messages, GET /whatsapp/inbox).
// The message is read once on arrival with the mock extractor and kept. Like the backend (auto-report on),
// a complete reading is filed as a disruption at once; anything else waits for the owner.
import type { DisruptionCreate, IncomingMessage, IncomingMessageCreate } from '../types/contracts'
import { analyzeMockDisruption, createMockDisruption, fixtures, logMock, nextMessageId, state } from './db'
import { mockExtract } from './extract'

/** Same fixed text as the backend: the sender never sees the AI's reading. */
export const ACKNOWLEDGEMENT = 'Thanks, your message was received. The owner will confirm.'

const MATERIAL = ['supplier_id', 'resource_id', 'quantity_affected', 'new_arrival_date'] as const

/** The supplier contact the sender stands for: the contact reference, else the owner's saved name or an alias. */
function senderContact(body: IncomingMessageCreate): string | null {
  if (body.from_contact) return body.from_contact
  const saved = body.contact_name?.trim().toLowerCase()
  if (!saved) return null
  const supplier = fixtures.seed.suppliers.find((s) => [s.name, ...s.aliases].some((a) => a.toLowerCase() === saved))
  return supplier?.contact_reference ?? null
}

/** The report a complete reading stands for, or null if anything is missing or flagged. */
function reportFrom(message: IncomingMessage): DisruptionCreate | null {
  const { extraction } = message
  const d = extraction.draft_incident
  if (extraction.needs_clarification || extraction.unresolved_fields.length || !d.type) return null
  if (MATERIAL.some((field) => d[field] == null)) return null
  return {
    type: d.type,
    source: 'message',
    supplier_id: d.supplier_id,
    resource_id: d.resource_id,
    delivery_id: d.delivery_id,
    quantity_affected: d.quantity_affected,
    original_arrival_date: d.original_arrival_date,
    new_arrival_date: d.new_arrival_date,
    description: d.description || 'Reported on WhatsApp',
    raw_message: message.text,
  }
}

/** File the report, or link to the open disruption for the same delivery and new date. */
function fileReport(message: IncomingMessage, report: DisruptionCreate) {
  const details = { message_id: message.id, channel: message.channel, filed_automatically: true }
  const duplicate = state.disruptions.find(
    (d) =>
      !['closed', 'decided'].includes(d.status) &&
      d.incident.delivery_id === report.delivery_id &&
      d.incident.new_arrival_date === report.new_arrival_date,
  )
  if (duplicate) {
    Object.assign(message, { disruption_id: duplicate.id, report_outcome: 'duplicate' })
    logMock(duplicate.id, 'disruption_extracted', 'system', null, { ...details, duplicate: true })
    return
  }
  const { disruption } = createMockDisruption(report)
  Object.assign(message, { disruption_id: disruption.id, report_outcome: 'filed' })
  logMock(disruption.id, 'disruption_extracted', 'system', null, details)
  analyzeMockDisruption(disruption)
}

export function mockReceive(body: IncomingMessageCreate): IncomingMessage {
  const message: IncomingMessage = {
    id: nextMessageId(),
    channel: 'simulator',
    received_at: new Date().toISOString(),
    text: body.text,
    from_number: body.from_number ?? null,
    contact_name: body.contact_name ?? null,
    from_contact: body.from_contact ?? null,
    extraction: mockExtract(body.text, senderContact(body)),
    disruption_id: null,
    report_outcome: null,
    reply: ACKNOWLEDGEMENT,
  }
  state.inbox.push(message)
  const report = reportFrom(message)
  if (report) fileReport(message, report)
  return message
}
