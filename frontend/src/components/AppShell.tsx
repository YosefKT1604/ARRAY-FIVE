import { useQuery } from '@tanstack/react-query'
import { Link, Outlet } from 'react-router-dom'
import { getHealth } from '../api/endpoints'
import { API_MODE, DEMO_TODAY } from '../config'
import { formatDate } from '../lib/format'
import { cn } from '../lib/cn'
import { isDevMode } from '../state/devMode'
import { updateSession, useSession } from '../state/session'
import { USERS, type UserId } from '../types/contracts'
import { DevPanel } from './DevPanel'

const MODE_LABEL = { mock: 'Mock mode', hybrid: 'Hybrid mode', real: 'Real backend' } as const

function ModeBadge() {
  return (
    <span
      className="rounded-full border border-line bg-card px-2.5 py-1 text-xs font-medium text-muted"
      title="VITE_API_MODE"
    >
      {MODE_LABEL[API_MODE]}
    </span>
  )
}

function BackendBadge() {
  const { isSuccess, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 15_000,
    enabled: API_MODE !== 'mock',
    retry: false,
  })
  const { force500 } = useSession()
  if (API_MODE === 'mock') return null
  // The force-500 toggle blocks /health too, so say that, rather than claiming the backend is down.
  if (force500) {
    return <span className="rounded-full bg-warn-bg px-2.5 py-1 text-xs font-semibold text-warn">Simulated error (dev)</span>
  }
  const tone = isLoading ? 'bg-info-bg text-muted' : isSuccess ? 'bg-ok-bg text-ok' : 'bg-bad-bg text-bad'
  const text = isLoading ? 'Checking backend…' : isSuccess ? 'Backend connected' : 'Backend unreachable'
  return <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', tone)}>{text}</span>
}

function UserSwitcher() {
  const { userId } = useSession()
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted">Signed in as</span>
      <select
        value={userId}
        onChange={(e) => updateSession({ userId: e.target.value as UserId })}
        className="rounded-lg border border-line bg-card px-2 py-1.5 font-medium"
      >
        {USERS.map((u) => (
          <option key={u.id} value={u.id}>
            {u.name} ({u.role === 'owner' ? 'Owner' : 'Staff'})
          </option>
        ))}
      </select>
    </label>
  )
}

export function AppShell() {
  return (
    <div className="min-h-dvh">
      {API_MODE === 'mock' && (
        <div className="bg-warn-bg px-4 py-2 text-center text-sm font-medium text-warn" role="note">
          Demo data (mock). Nothing here is saved to a server.
        </div>
      )}
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <Link to="/" className="font-display text-xl font-semibold text-brand">
            SCDC <span className="text-sm font-normal text-muted">Recovery</span>
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-muted" title="Relative dates are measured from this day">
              Demo date: {formatDate(DEMO_TODAY)}
            </span>
            <BackendBadge />
            <ModeBadge />
            <UserSwitcher />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:py-8">
        <Outlet />
      </main>
      {isDevMode() && <DevPanel />}
    </div>
  )
}
