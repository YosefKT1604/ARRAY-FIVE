import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ActivityLog } from './pages/ActivityLog'
import { Drafts } from './pages/Drafts'
import { NotFound } from './pages/NotFound'
import { Dashboard } from './pages/Dashboard'
import { Impact } from './pages/Impact'
import { PlanReview } from './pages/PlanReview'
import { Plans } from './pages/Plans'
import { ReportDisruption } from './pages/ReportDisruption'
import { WhatsAppSimulator } from './pages/WhatsAppSimulator'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/report', element: <ReportDisruption /> },
      { path: '/whatsapp', element: <WhatsAppSimulator /> },
      { path: '/disruptions/:id/impact', element: <Impact /> },
      { path: '/disruptions/:id/plans', element: <Plans /> },
      { path: '/plans/:planId', element: <PlanReview /> },
      { path: '/plans/:planId/drafts', element: <Drafts /> },
      { path: '/disruptions/:id/log', element: <ActivityLog /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
