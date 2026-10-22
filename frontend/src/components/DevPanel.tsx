import { useQueryClient } from '@tanstack/react-query'
import { API_MODE } from '../config'
import { resetMockState } from '../mocks/db'
import { updateSession, useSession, type ScenarioId } from '../state/session'

/** Developer controls. Only rendered when the URL has ?dev=1 (see state/devMode.ts). Starts collapsed. */
export function DevPanel() {
  const session = useSession()
  const queryClient = useQueryClient()

  return (
    <details className="group fixed bottom-2 left-2 z-50 w-fit max-w-[calc(100vw-1rem)] rounded-full border border-line bg-card/95 text-sm shadow-lg open:w-72 open:rounded-xl">
      <summary className="cursor-pointer list-none px-3 py-1 text-xs font-semibold whitespace-nowrap text-muted [&::-webkit-details-marker]:hidden">
        ⚙ Dev
      </summary>
      <div className="max-h-[70vh] space-y-3 overflow-y-auto border-t border-line p-3">
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

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={session.staffCanTry}
            onChange={(e) => updateSession({ staffCanTry: e.target.checked })}
          />
          Let Staff press Approve (shows the 403)
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
          <p className="mt-1">Real backend (Windows). This wipes every disruption and plan:</p>
          <ol className="mt-1 list-decimal space-y-1 pl-4">
            <li>Stop the backend (Ctrl+C in its terminal).</li>
            <li>
              In <code>ARRAY-FIVE-backend\src\backend</code> run <code>python -m uv run python -m app.db.seed</code>
            </li>
            <li>Start the backend again.</li>
            <li>Reload this page.</li>
          </ol>
          <p className="mt-1">Mock mode: use "Reset mock data" above (a reload keeps your progress; closing the tab clears it).</p>
        </div>
      </div>
    </details>
  )
}
