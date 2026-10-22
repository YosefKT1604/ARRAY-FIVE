export type ApiMode = 'mock' | 'hybrid' | 'real'

const raw = import.meta.env.VITE_API_MODE as string | undefined

export const API_MODE: ApiMode = raw === 'mock' || raw === 'real' ? raw : 'hybrid'
export const API_BASE = '/api/v1'
export const TIME_ZONE = 'Asia/Kuala_Lumpur'
