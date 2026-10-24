import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import incident from '../../../fixtures/demo/incident.json'
import { describeActivity } from '../lib/activity'
import { resetMockState, state } from '../mocks/db'
import { server } from '../mocks/server'
import { ACKNOWLEDGEMENT, mockReceive } from '../mocks/whatsapp'
import { ReportDisruption } from '../pages/ReportDisruption'
import { WhatsAppSimulator } from '../pages/WhatsAppSimulator'
import type { ActivityLogEntry } from '../types/contracts'

const realFetch = globalThis.fetch
beforeAll(() => {
  // jsdom has no base URL for Node's fetch; give relative API paths one so MSW can answer them.
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === 'string' && input.startsWith('/') ? `http://localhost${input}` : input, init)) as typeof fetch
  server.listen({ onUnhandledFrame: 'error' })
})
beforeEach(() => resetMockState())
afterEach(() => server.resetHandlers())
afterAll(() => {
  server.close()
  globalThis.fetch = realFetch
})

function renderPage(page: React.ReactNode = <WhatsAppSimulator />, path = '/whatsapp') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('mock WhatsApp inbox', () => {
  it('reads the demo message from Maju and answers with the fixed text', () => {
    const m = mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    expect(m.id).toBe('WA-001')
    expect(m.reply).toBe(ACKNOWLEDGEMENT)
    expect(m.extraction.draft_incident).toMatchObject({ supplier_id: 'S-01', resource_id: 'R-01', quantity_affected: 20 })
  })

  it("uses the owner's saved name when there is no contact reference", () => {
    const m = mockReceive({ text: incident.supplier_message.text, from_number: '+60 12-345 6789', contact_name: 'Maju' })
    expect(m.extraction.draft_incident.supplier_id).toBe('S-01')
  })
})

describe('WhatsApp simulator page', () => {
  it('sends the demo message, shows the auto-reply, and lists it in the inbox', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Use the demo message' }))
    await user.click(screen.getByRole('button', { name: 'Send' }))

    const chat = screen.getByRole('log', { name: 'Chat' })
    expect(await within(chat).findByText(ACKNOWLEDGEMENT)).toBeInTheDocument()

    const inbox = screen.getByRole('region', { name: "Owner's inbox" })
    expect(await within(inbox).findByText('Maju Rental Supplies')).toBeInTheDocument()
    expect(within(inbox).getByText(/We read:/).parentElement).toHaveTextContent('Maju Rental Supplies · 20 Folding Chairs · new date Fri 23 Oct')
  })

  it('says why a reading was not filed', async () => {
    mockReceive({ text: incident.supplier_message.text })
    state.inbox[0].not_filed_reasons = ['500 chairs is more than the 40 on this delivery.']
    renderPage()
    expect(await screen.findByText('Not filed: 500 chairs is more than the 40 on this delivery.')).toBeInTheDocument()
  })

  it('only offers saved supplier contacts in "Send as"', async () => {
    renderPage()
    const select = await screen.findByRole('combobox', { name: 'Send as' })
    await within(select).findByRole('option', { name: 'Maju Rental Supplies' })
    expect(within(select).queryByRole('option', { name: /Someone else/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Phone number' })).not.toBeInTheDocument()
  })
})

describe('Create report from the inbox', () => {
  it('links an incomplete message to the report form', async () => {
    mockReceive({ text: incident.supplier_message.text })
    renderPage()
    expect(await screen.findByRole('link', { name: 'Check and report' })).toHaveAttribute('href', '/report?message=WA-001')
  })

  it('fills the report form from the stored reading', async () => {
    mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    renderPage(<ReportDisruption />, '/report?message=WA-001')
    expect(await screen.findByText(/Filled in from WhatsApp message WA-001/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Supplier message' })).toHaveValue(incident.supplier_message.text)
    expect(await screen.findByRole('combobox', { name: /Which supplier is late/ })).toHaveValue('S-01')
    expect(screen.getByRole('spinbutton', { name: /How many/ })).toHaveValue(20)
    expect(screen.getByLabelText(/Now arriving on/)).toHaveValue('2026-10-23')
  })

  it('says so when the message does not exist', async () => {
    renderPage(<ReportDisruption />, '/report?message=WA-099')
    expect(await screen.findByText(/WA-099 was not found/)).toBeInTheDocument()
  })
})

describe('automatic reports from WhatsApp', () => {
  it('files a complete reading as a disruption and analyzes it', () => {
    const m = mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    expect([m.disruption_id, m.report_outcome]).toEqual(['D-001', 'filed'])
    expect(state.disruptions[0]).toMatchObject({ id: 'D-001', source: 'message', status: 'analyzed' })
    expect(state.activity.find((a) => a.activity_type === 'disruption_extracted')?.details).toEqual({
      message_id: 'WA-001',
      channel: 'simulator',
      filed_automatically: true,
    })
  })

  it('links a repeat to the open report instead of filing it again', () => {
    mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    const again = mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    expect([again.disruption_id, again.report_outcome]).toEqual(['D-001', 'duplicate'])
    expect(state.disruptions).toHaveLength(1)
  })

  it('leaves an incomplete reading for the owner', () => {
    const m = mockReceive({ text: incident.supplier_message.text })
    expect(m.disruption_id).toBeNull()
    expect(state.disruptions).toHaveLength(0)
  })

  it('shows "Reported automatically. See the problem" in the inbox, with no ID', async () => {
    mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    renderPage()
    expect(await screen.findByText(/Reported automatically\./)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See the problem' })).toHaveAttribute('href', '/disruptions/D-001/impact')
    expect(screen.queryByText(/D-001/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Check and report' })).not.toBeInTheDocument()
  })

  it('describes the log entry in plain words', () => {
    const ctx = { humanize: (t: string) => t, planTitle: () => undefined, disruptionDescription: undefined }
    const entry = { id: 'LOG-0002', disruption_id: 'D-001', plan_id: null, actor_id: 'system', activity_type: 'disruption_extracted', created_at: '', details: { message_id: 'WA-001', filed_automatically: true } }
    expect(describeActivity(entry as ActivityLogEntry, ctx)).toBe("The supplier's WhatsApp message was read and this report was filed automatically.")
  })
})
