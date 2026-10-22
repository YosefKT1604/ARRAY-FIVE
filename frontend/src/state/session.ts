import { useSyncExternalStore } from 'react'
import type { UserId } from '../types/contracts'

export type ScenarioId = 'main' | 'no_feasible'

export interface Session {
  userId: UserId
  force500: boolean
  scenario: ScenarioId
}

const KEY = 'scdc.session'
const defaults: Session = { userId: 'U-01', force500: false, scenario: 'main' }

function load(): Session {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...defaults, ...JSON.parse(raw), force500: false }
  } catch {
    /* storage unavailable: use defaults */
  }
  return defaults
}

let session: Session = load()
const listeners = new Set<() => void>()

export function getSession(): Session {
  return session
}

export function updateSession(patch: Partial<Session>) {
  session = { ...session, ...patch }
  try {
    localStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useSession(): Session {
  return useSyncExternalStore(subscribe, getSession)
}
