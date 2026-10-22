import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ComingSoon } from './pages/ComingSoon'
import { Dashboard } from './pages/Dashboard'
import { Impact } from './pages/Impact'
import { ReportDisruption } from './pages/ReportDisruption'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/report', element: <ReportDisruption /> },
      { path: '/disruptions/:id/impact', element: <Impact /> },
      { path: '/disruptions/:id/plans', element: <ComingSoon title="Recovery plans" milestone="M3" /> },
      { path: '/plans/:planId', element: <ComingSoon title="Plan review" milestone="M3" /> },
      { path: '/plans/:planId/drafts', element: <ComingSoon title="Drafts" milestone="M4" /> },
      { path: '/disruptions/:id/log', element: <ComingSoon title="Activity log" milestone="M4" /> },
      { path: '*', element: <ComingSoon title="Page not found" milestone="n/a" /> },
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
