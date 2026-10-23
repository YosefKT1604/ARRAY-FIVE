import { defineConfig } from '@playwright/test'

// Mock mode, its own dev server on its own port: deterministic, needs no backend.
// Playwright starts the server before the test and stops it afterwards.
const PORT = 5199

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  workers: 1,
  reporter: 'list',
  use: { baseURL: `http://localhost:${PORT}`, viewport: { width: 1100, height: 900 } },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    env: { VITE_API_MODE: 'mock' },
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
