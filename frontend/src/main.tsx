import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { API_MODE } from './config'
import './index.css'

async function enableMocking() {
  if (API_MODE === 'real') return
  const { worker } = await import('./mocks/browser')
  // 'bypass' (MSW 3 name: onUnhandledFrame): anything we have no mock for goes to the real backend (via the Vite proxy).
  await worker.start({ onUnhandledFrame: 'bypass', quiet: true })
}

void enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
