import { setupWorker } from 'msw/browser'
import { API_MODE } from '../config'
import { hybridOverlayHandlers, missingEndpointHandlers, mockedBackendHandlers } from './handlers'

/**
 * mock:   MSW answers everything.
 * hybrid: MSW answers only what the backend lacks (plus demo-only overlays); the rest passes through.
 * real:   MSW is never started.
 */
export const handlers =
  API_MODE === 'mock'
    ? [...mockedBackendHandlers, ...missingEndpointHandlers]
    : [...missingEndpointHandlers, ...hybridOverlayHandlers]

export const worker = setupWorker(...handlers)
