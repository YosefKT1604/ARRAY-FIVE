/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // fixtures/ lives one level above frontend/
    fs: { allow: ['..'] },
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    // Tests always run against the mocks, whatever the developer's own VITE_API_MODE is.
    env: { VITE_API_MODE: 'mock' },
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
