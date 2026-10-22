import { setupWorker } from 'msw/browser'
import { API_MODE } from '../config'
import { missingEndpointHandlers, mockedBackendHandlers } from './handlers'

/** mock: MSW answers everything. hybrid: only what the backend lacks. real: MSW is never started. */
export const handlers = API_MODE === 'mock' ? [...mockedBackendHandlers, ...missingEndpointHandlers] : missingEndpointHandlers

export const worker = setupWorker(...handlers)
