import { setupServer } from 'msw/node'
import { missingEndpointHandlers, mockedBackendHandlers } from './handlers'

/** For Vitest: everything is mocked, regardless of VITE_API_MODE. */
export const server = setupServer(...mockedBackendHandlers, ...missingEndpointHandlers)
