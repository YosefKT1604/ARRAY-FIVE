export type ApiMode = 'mock' | 'hybrid' | 'real'

const raw = import.meta.env.VITE_API_MODE as string | undefined

export const API_MODE: ApiMode = raw === 'mock' || raw === 'real' ? raw : 'hybrid'
export const API_BASE = '/api/v1'
export const TIME_ZONE = 'Asia/Kuala_Lumpur'

/**
 * The demo clock: the seed's `as_of` date (2026-10-20T08:00+08:00). Everything relative
 * ("in 2 days", upcoming vs past) is measured from this day, never from the real calendar.
 */
export const DEMO_TODAY = '2026-10-20'
