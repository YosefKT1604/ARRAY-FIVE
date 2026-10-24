import { setupWorker } from 'msw/browser'
import { API_MODE } from '../config'
import { hybridOverlayHandlers, missingEndpointHandlers, mockedBackendHandlers } from './handlers'

/**
 * mock:   MSW answers everything.
 * hybrid: the backend now has every endpoint, so MSW only keeps its overlays (which pass through unless a mock edit exists).
 * real:   MSW is never started.
 */
export const handlers =
  API_MODE === 'mock'
    ? [...mockedBackendHandlers, ...missingEndpointHandlers]
    : [...hybridOverlayHandlers]

export const worker = setupWorker(...handlers)
