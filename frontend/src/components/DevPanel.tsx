import { useQueryClient } from '@tanstack/react-query'
import { API_MODE } from '../config'
import { resetMockState } from '../mocks/db'
import { updateSession, useSession, type ScenarioId } from '../state/session'

/** Development-only controls. Not rendered in production builds. */
export function DevPanel() {
  const session = useSession()
  const queryClient = useQueryClient()

  return (
    <details className="fixed right-3 bottom-3 z-50 w-72 rounded-xl border border-line bg-card text-sm shadow-lg">
      <summary className="cursor-pointer px-3 py-2 font-semibold text-muted">Dev panel</summary>
      <div className="space-y-3 border-t border-line p-3">
        <label className="block">
          <span className="text-muted">Mock scenario</span>
          <select
            value={session.scenario}
            onChange={(e) => updateSession({ scenario: e.target.value as ScenarioId })}
            className="mt-1 w-full rounded-lg border border-line bg-paper px-2 py-1.5"
          >
            <option value="main">A: main demo</option>
            <option value="no_feasible" disabled>
              B: no feasible option (MOCK-ONLY, coming in M4)
            </option>
          </select>
        </label>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={session.force500}
            onChange={(e) => {
              updateSession({ force500: e.target.checked })
              void queryClient.invalidateQueries()
            }}
          />
          Force a 500 error on every call
        </label>

        {API_MODE === 'mock' && (
          <button
            onClick={() => {
              resetMockState()
              void queryClient.invalidateQueries()
            }}
            className="w-full rounded-lg border border-line bg-paper px-3 py-1.5 font-medium hover:bg-white"
          >
            Reset mock data
          </button>
        )}

        <div className="rounded-lg bg-info-bg p-2 text-xs leading-relaxed text-ink">
          <p className="font-semibold">How to reset the demo</p>
          <p className="mt-1">
            Real backend: in the backend folder <code>src/backend</code> run{' '}
            <code>uv run python -m app.db.seed</code>. This wipes every disruption and plan. Then reload this page.
          </p>
          <p className="mt-1">Mock mode: use "Reset mock data" above, or just reload the page.</p>
        </div>
      </div>
    </details>
  )
}
