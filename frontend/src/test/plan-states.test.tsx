import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import incident from '../../../fixtures/demo/incident.json'
import { API_BASE } from '../config'
import { analyzeMockDisruption, createMockDisruption, resetMockState } from '../mocks/db'
import { server } from '../mocks/server'
import { Dashboard } from '../pages/Dashboard'
import { Impact } from '../pages/Impact'
import { Plans } from '../pages/Plans'
import { ReportDisruption } from '../pages/ReportDisruption'
import type { DisruptionCreate, PlanState } from '../types/contracts'

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

const url = (path: string) => `${API_BASE}${path}`

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/report" element={<ReportDisruption />} />
          <Route path="/disruptions/:id/impact" element={<Impact />} />
          <Route path="/disruptions/:id/plans" element={<Plans />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** An analyzed demo problem, as the backend leaves it before plans are asked for. */
function analyzedProblem() {
  const { disruption } = createMockDisruption(incident.form_input as DisruptionCreate)
  analyzeMockDisruption(disruption)
  return disruption
}

/** The backend answers the plan list with no plans and the reason. */
function planListSays(state: PlanState) {
  server.use(http.get(url('/disruptions/:id/recovery-plans'), () => HttpResponse.json({ items: [], state })))
}

const NOTHING = 'Nothing to recover: no event is affected.'
const NOT_YET = "We can't suggest plans for this case yet. Check the open questions."
const UNCLEAR = 'The facts are unclear. Confirm them first.'

describe('plans screen without plans', () => {
  it('says nothing needs recovering, in green', async () => {
    const d = analyzedProblem()
    d.status = 'plans_ready'
    planListSays('no_recovery_needed')
    renderAt(`/disruptions/${d.id}/plans`)
    const notice = await screen.findByText(NOTHING)
    expect(notice.closest('[data-testid="plan-state-notice"]')).toHaveClass('bg-ok-bg')
    expect(screen.queryByRole('button', { name: 'Find recovery options' })).not.toBeInTheDocument()
  })

  it('says plans cannot be suggested yet, in amber', async () => {
    const d = analyzedProblem()
    d.status = 'plans_ready'
    planListSays('planning_not_available')
    renderAt(`/disruptions/${d.id}/plans`)
    const notice = await screen.findByText(NOT_YET)
    expect(notice.closest('[data-testid="plan-state-notice"]')).toHaveClass('bg-warn-bg')
  })

  it('says the facts are unclear when planning is refused, with a link back to the impact screen', async () => {
    const d = analyzedProblem()
    server.use(
      http.post(url('/disruptions/:id/recovery-plans'), () =>
        HttpResponse.json(
          {
            title: 'Conflict',
            status: 409,
            detail: 'The impact could not be decided; confirm the facts first.',
            code: 'INVALID_STATE_TRANSITION',
          },
          { status: 409 },
        ),
      ),
    )
    renderAt(`/disruptions/${d.id}/plans`)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Find recovery options' }))
    const notice = await screen.findByText(UNCLEAR)
    expect(notice.closest('[data-testid="plan-state-notice"]')).toHaveClass('bg-warn-bg')
    expect(screen.getByRole('link', { name: 'Back to what this affects' })).toHaveAttribute('href', `/disruptions/${d.id}/impact`)
    expect(screen.queryByText(/could not be decided/)).not.toBeInTheDocument()
  })
})

describe('dashboard', () => {
  it('shows the reason on a problem that has no plans', async () => {
    const d = analyzedProblem()
    d.status = 'plans_ready'
    d.plan_state = 'planning_not_available'
    renderAt('/')
    expect(await screen.findByText(NOT_YET)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See impact' })).toHaveAttribute('href', `/disruptions/${d.id}/impact`)
    expect(screen.queryByTestId('decision-card')).not.toBeInTheDocument()
  })

  it('shows the unclear-facts notice with its link', async () => {
    const d = analyzedProblem()
    d.plan_state = 'impact_unclear'
    renderAt('/')
    expect(await screen.findByText(UNCLEAR)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to what this affects' })).toHaveAttribute('href', `/disruptions/${d.id}/impact`)
  })

  it('shows the green all-clear', async () => {
    const d = analyzedProblem()
    d.status = 'plans_ready'
    d.plan_state = 'no_recovery_needed'
    renderAt('/')
    expect(await screen.findByText(NOTHING)).toBeInTheDocument()
  })
})

describe('impact screen', () => {
  it('shows the unclear-facts notice when planning is refused', async () => {
    const d = analyzedProblem()
    server.use(
      http.post(url('/disruptions/:id/recovery-plans'), () =>
        HttpResponse.json(
          { title: 'Conflict', status: 409, detail: 'The impact could not be decided; confirm the facts first.', code: 'INVALID_STATE_TRANSITION' },
          { status: 409 },
        ),
      ),
    )
    renderAt(`/disruptions/${d.id}/impact`)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'See recovery options' }))
    expect(await screen.findByText(UNCLEAR)).toBeInTheDocument()
  })
})

describe('report form', () => {
  it('shows each field error next to its field', async () => {
    server.use(
      http.post(url('/disruptions'), () =>
        HttpResponse.json(
          {
            title: 'Unprocessable Content',
            status: 422,
            detail: 'Some details need fixing.',
            code: 'VALIDATION_ERROR',
            errors: [
              { loc: ['body', 'quantity_affected'], msg: '500 chairs is more than the 40 on this delivery.', type: 'value_error' },
              { loc: ['body', 'delivery_id'], msg: 'This order does not include the item you chose.', type: 'value_error' },
            ],
          },
          { status: 422 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderAt('/report')
    await screen.findAllByRole('option', { name: 'Maju Rental Supplies' })
    await user.selectOptions(screen.getByRole('combobox', { name: /Which supplier is late/ }), 'Maju Rental Supplies')
    await user.selectOptions(screen.getByRole('combobox', { name: /What is affected/ }), 'Folding Chairs')
    await user.type(screen.getByRole('spinbutton', { name: /How many/ }), '500')
    await user.type(screen.getByLabelText(/Now arriving on/), '2026-10-23')
    await user.click(screen.getByRole('button', { name: 'Report and check impact' }))

    const quantity = await screen.findByText('500 chairs is more than the 40 on this delivery.')
    expect(quantity.parentElement).toContainElement(screen.getByRole('spinbutton', { name: /How many/ }))
    const order = screen.getByText('This order does not include the item you chose.')
    expect(order.parentElement).toContainElement(screen.getByRole('combobox', { name: /Which order is delayed/ }))
  })
})
