import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import incident from '../../../fixtures/demo/incident.json'
import { plainQuestion } from '../lib/questions'
import { createMockDisruption, logMock, resetMockState, state } from '../mocks/db'
import { mockReceive } from '../mocks/whatsapp'
import { mockExtract } from '../mocks/extract'
import { server } from '../mocks/server'
import { ActivityLog } from '../pages/ActivityLog'
import { ReportDisruption } from '../pages/ReportDisruption'
import type { ExtractionResult } from '../types/contracts'

vi.setConfig({ testTimeout: 20_000 })

const realFetch = globalThis.fetch
beforeAll(() => {
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

function renderAt(path: string, page: React.ReactNode, route = '*') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={page} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const MIXED_MESSAGE = 'Hi boss, 15 tables and 7 chairs will not be able to be shipped tomorrow'

/** What the real backend returns for MIXED_MESSAGE (see Person 5's question()). */
function mixedExtraction(): ExtractionResult {
  const base = mockExtract(MIXED_MESSAGE, null)
  const unresolved = [
    { field: 'resource_id', reason: 'ambiguous', raw_value: null, candidates: ['R-01', 'R-02'], note: 'matches more than one record' },
    { field: 'quantity_affected', reason: 'conflicting', raw_value: null, candidates: ['7', '15'], note: 'the message gives different quantities: 7, 15' },
  ] as ExtractionResult['unresolved_fields']
  return {
    ...base,
    unresolved_fields: unresolved,
    needs_clarification: true,
    clarification_questions: [
      'Please confirm the affected item: matches more than one record. Suggestions: R-01, R-02.',
      'Please confirm how many units are affected: the message gives different quantities: 7, 15. Suggestions: 7, 15.',
    ],
  }
}

describe('activity log times', () => {
  it('shows the time of day once and never the real date', async () => {
    const { disruption } = createMockDisruption({
      type: 'supplier_delay', source: 'form', supplier_id: 'S-01', resource_id: 'R-01', delivery_id: 'D-01',
      quantity_affected: 20, original_arrival_date: '2026-10-21', new_arrival_date: '2026-10-23', description: 'Late chairs', raw_message: null,
    } as never)
    logMock(disruption.id, 'plan_revalidated', 'system', null)
    // 9:12 pm in Kuala Lumpur on the real Saturday, long after the demo clock (Tue 20 Oct, 08:00).
    state.activity[state.activity.length - 1].created_at = '2026-10-24T13:12:00Z'
    renderAt(`/disruptions/${disruption.id}/log`, <ActivityLog />, '/disruptions/:id/log')
    const times = await screen.findAllByText(/\d{1,2}:\d{2}/)
    const shown = times.map((t) => t.textContent ?? '')
    expect(shown.some((t) => /9:12\s?pm/i.test(t))).toBe(true)
    for (const t of shown) {
      expect(t).not.toMatch(/Sat|Oct/)
      expect((t.match(/\d{1,2}:\d{2}/g) ?? []).length).toBe(1)
    }
  })
})

describe('plainQuestion', () => {
  const humanize = (t: string) => ({ 'R-01': 'Folding Chairs', 'R-02': 'Round Tables (10-seat)' })[t] ?? t

  it('names the suggestions', () => {
    expect(plainQuestion('Please confirm the affected item: matches more than one record. Suggestions: R-01, R-02.', humanize)).toBe(
      'Please confirm the affected item: matches more than one record. Suggestions: Folding Chairs or Round Tables (10-seat).',
    )
  })

  it('asks about two numbers once', () => {
    expect(plainQuestion('Please confirm how many units are affected: the message gives different quantities: 7, 15. Suggestions: 7, 15.', humanize)).toBe(
      'The message gives two numbers (7 and 15). Which one is for this item?',
    )
  })
})

describe('report form with an unclear message', () => {
  beforeEach(() => {
    server.use(http.post('*/disruptions/extract', () => HttpResponse.json(mixedExtraction())))
  })

  it('shows item names, asks about the numbers once, and tips that one report covers one item', async () => {
    const user = userEvent.setup()
    renderAt('/report', <ReportDisruption />)
    await user.click(screen.getByRole('textbox', { name: 'Supplier message' }))
    await user.paste(MIXED_MESSAGE)
    await user.click(screen.getByRole('button', { name: 'Read message' }))
    expect(await screen.findByText(/This message mentions more than one item\. One report covers one item/)).toBeInTheDocument()
    expect(await screen.findByText(/Suggestions: Folding Chairs or Round Tables \(10-seat\)\./)).toBeInTheDocument()
    expect(screen.getByText('The message gives two numbers (7 and 15). Which one is for this item?')).toBeInTheDocument()
    expect(screen.queryByText(/R-01|R-02|Suggestions: 7/)).not.toBeInTheDocument()
  })
})

describe('"Who sent it?"', () => {
  const senderBox = () => screen.getByRole('combobox', { name: /Who sent it/ })

  it('lists the saved suppliers, sends the chosen contact reference, and sends nothing for "Not sure"', async () => {
    const user = userEvent.setup()
    const sent: (string | null | undefined)[] = []
    server.use(
      http.post('*/disruptions/extract', async ({ request }) => {
        sent.push(((await request.json()) as { from_contact?: string | null }).from_contact)
        return HttpResponse.json(mockExtract(MIXED_MESSAGE, null))
      }),
    )
    renderAt('/report', <ReportDisruption />)
    await screen.findAllByRole('option', { name: 'Maju Rental Supplies' })
    const options = Array.from(senderBox().querySelectorAll('option')).map((o) => o.textContent)
    expect(options[0]).toBe('Not sure')
    expect(options).toContain('Maju Rental Supplies')
    expect(senderBox()).toHaveValue('')

    await user.click(screen.getByRole('textbox', { name: 'Supplier message' }))
    await user.paste(MIXED_MESSAGE)
    await user.click(screen.getByRole('button', { name: 'Read message' }))
    await screen.findByText(/Message read/)
    expect(sent[0] == null || sent[0] === '').toBe(true)

    await user.selectOptions(senderBox(), 'Maju Rental Supplies')
    await user.click(screen.getByRole('button', { name: 'Read message' }))
    await screen.findAllByText(/Message read/)
    await vi.waitFor(() => expect(sent).toHaveLength(2))
    expect(sent[1]).toBe(incident.supplier_message.from_contact)
  })

  it('"Use the demo message" selects Maju, and typing a different message clears the sender', async () => {
    const user = userEvent.setup()
    renderAt('/report', <ReportDisruption />)
    await screen.findAllByRole('option', { name: 'Maju Rental Supplies' })
    await user.click(screen.getByRole('button', { name: 'Use the demo message' }))
    const maju = Array.from(senderBox().querySelectorAll('option')).find((o) => o.textContent === 'Maju Rental Supplies')
    expect(senderBox()).toHaveValue(maju!.getAttribute('value'))

    await user.click(screen.getByRole('textbox', { name: 'Supplier message' }))
    await user.paste(' extra')
    expect(senderBox()).toHaveValue('')
  })

  it('preselects the sender when a WhatsApp message is opened from the inbox', async () => {
    const m = mockReceive({ text: incident.supplier_message.text, from_contact: incident.supplier_message.from_contact })
    renderAt(`/report?message=${m.id}`, <ReportDisruption />)
    await screen.findByText(/Filled in from the supplier's WhatsApp message/)
    await vi.waitFor(() => expect((senderBox() as HTMLSelectElement).selectedOptions[0]?.textContent).toBe('Maju Rental Supplies'))
  })

  it('fills the supplier from the sender when the message names none, without the "no known suppliers" question', async () => {
    const user = userEvent.setup()
    renderAt('/report', <ReportDisruption />)
    await screen.findAllByRole('option', { name: 'Maju Rental Supplies' })
    await user.selectOptions(senderBox(), 'Maju Rental Supplies')
    await user.click(screen.getByRole('textbox', { name: 'Supplier message' }))
    await user.paste('Boss, 20 chairs will be late, now Friday')
    await user.click(screen.getByRole('button', { name: 'Read message' }))
    await screen.findByText(/Message read/)
    await vi.waitFor(() => expect(screen.getByLabelText(/Which supplier is late/)).toHaveValue('S-01'))
    expect(screen.queryByText(/does not name any known suppliers/i)).not.toBeInTheDocument()
  })
})

describe('hints under the form fields', () => {
  it('read as a clean sentence with the same wording as the box at the top', async () => {
    const user = userEvent.setup()
    const mixed = mixedExtraction()
    mixed.draft_incident = { ...mixed.draft_incident, resource_id: null, quantity_affected: null }
    server.use(http.post('*/disruptions/extract', () => HttpResponse.json(mixed)))
    renderAt('/report', <ReportDisruption />)
    await user.click(screen.getByRole('textbox', { name: 'Supplier message' }))
    await user.paste(MIXED_MESSAGE)
    await user.click(screen.getByRole('button', { name: 'Read message' }))
    await screen.findByText(/Message read/)
    expect(screen.queryByText(/Please fill this in/)).not.toBeInTheDocument()
    expect(screen.queryByText(/different quantities: 7, 15/)).not.toBeInTheDocument()
    expect(screen.getAllByText('The message gives two numbers (7 and 15). Which one is for this item?').length).toBe(2)
  })

  it('turn a bare backend note into a sentence', async () => {
    const user = userEvent.setup()
    const base = mockExtract('hello', null)
    server.use(
      http.post('*/disruptions/extract', () =>
        HttpResponse.json({
          ...base,
          unresolved_fields: [{ field: 'supplier_id', reason: 'missing', raw_value: null, candidates: [], note: 'the message does not name any known suppliers' }],
          clarification_questions: [],
        }),
      ),
    )
    renderAt('/report', <ReportDisruption />)
    await user.click(screen.getByRole('textbox', { name: 'Supplier message' }))
    await user.paste('hello')
    await user.click(screen.getByRole('button', { name: 'Read message' }))
    expect(await screen.findByText('The message does not name any known suppliers. Please fill this in.')).toBeInTheDocument()
  })
})
