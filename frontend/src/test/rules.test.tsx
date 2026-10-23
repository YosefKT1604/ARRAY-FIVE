import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { MoneyText } from '../components/MoneyText'
import { StatusBadge } from '../components/StatusBadge'
import { useNames } from '../lib/useNames'
import { analyzeMockDisruption, createMockDisruption, fixtures, generateMockPlans, resetMockState } from '../mocks/db'
import { server } from '../mocks/server'
import { PlanReview } from '../pages/PlanReview'
import { updateSession } from '../state/session'
import type { DisruptionCreate, RecoveryPlan } from '../types/contracts'

const realFetch = globalThis.fetch
beforeAll(() => {
  // jsdom has no base URL for Node's fetch; give relative API paths one so MSW can answer them.
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === 'string' && input.startsWith('/') ? `http://localhost${input}` : input, init)) as typeof fetch
  server.listen({ onUnhandledFrame: 'error' })
})
afterEach(() => server.resetHandlers())
afterAll(() => {
  server.close()
  globalThis.fetch = realFetch
})

function wrap(ui: React.ReactNode, path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/plans/:planId" element={ui} />
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('status badge words', () => {
  it.each([
    ['feasible', 'Checked: works with known data'],
    ['needs_confirmation', 'Needs confirmation'],
    ['infeasible', "Won't work"],
  ] as const)('%s reads "%s"', (status, words) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(words)).toHaveAttribute('data-status', status)
  })
})

describe('money', () => {
  it('shows RM 80.00 for a known cost', () => {
    render(<MoneyText value={{ amount: '80.00', currency: 'MYR' }} />)
    expect(screen.getByText('RM 80.00')).toBeInTheDocument()
  })
  it('shows "Cost unknown" for null, never RM 0.00', () => {
    render(<MoneyText value={null} />)
    expect(screen.getByText('Cost unknown')).toBeInTheDocument()
    expect(screen.queryByText(/RM 0/)).not.toBeInTheDocument()
  })
})

describe('humanized text', () => {
  function Sample() {
    const names = useNames()
    return <p>{names.humanize('S-01 will arrive on 2026-10-22 with DL-01')}</p>
  }
  it('turns IDs and ISO dates into names and "Thu 22 Oct"', async () => {
    wrap(<Sample />)
    await waitFor(() => expect(screen.getByText(/Maju/)).toBeInTheDocument())
    const text = screen.getByText(/Maju/).textContent ?? ''
    expect(text).toContain('Thu 22 Oct')
    expect(text).not.toMatch(/S-01|DL-01|2026-10-22/)
  })
})

describe('plan review decisions', () => {
  let plans: RecoveryPlan[]
  beforeEach(() => {
    resetMockState()
    const f = fixtures.incident.form_input as unknown as DisruptionCreate
    const { disruption } = createMockDisruption(f)
    analyzeMockDisruption(disruption)
    plans = generateMockPlans(disruption)
    updateSession({ userId: 'U-01' })
  })

  const approveButton = () => screen.getByRole('button', { name: /^approve/i })

  it('disables Approve on an infeasible plan and says why', async () => {
    const infeasible = plans.find((p) => p.validation?.status === 'infeasible')!
    wrap(<PlanReview />, `/plans/${infeasible.id}`)
    await screen.findByText("Won't work")
    expect(approveButton()).toBeDisabled()
    expect(screen.getByTestId('blocked-reason')).toHaveTextContent("can't be approved")
  })

  it('lets the owner approve a feasible plan', async () => {
    const feasible = plans.find((p) => p.validation?.status === 'feasible')!
    wrap(<PlanReview />, `/plans/${feasible.id}`)
    await screen.findByText('Checked: works with known data')
    expect(approveButton()).toBeEnabled()
  })

  it('stops Staff from deciding, with the reason shown', async () => {
    updateSession({ userId: 'U-02' })
    const feasible = plans.find((p) => p.validation?.status === 'feasible')!
    wrap(<PlanReview />, `/plans/${feasible.id}`)
    await screen.findByText("Waiting for the owner's decision")
    expect(approveButton()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled()
    expect(screen.getByTestId('blocked-reason')).toHaveTextContent('Only the business owner')
  })
})
