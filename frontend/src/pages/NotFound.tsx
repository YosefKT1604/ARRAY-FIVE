import { Link } from 'react-router-dom'
import { EmptyState } from '../components/states'

export function NotFound() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <EmptyState title="We can't find that page">The link may be old, or the demo may have been reset.</EmptyState>
      <Link to="/" className="text-sm font-semibold text-brand underline">
        Back to dashboard
      </Link>
    </div>
  )
}
