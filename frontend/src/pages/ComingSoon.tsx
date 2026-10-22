import { Link } from 'react-router-dom'
import { EmptyState } from '../components/states'

/** Placeholder for screens built in later milestones. */
export function ComingSoon({ title, milestone }: { title: string; milestone: string }) {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <EmptyState title="Not built yet">This screen arrives in milestone {milestone}.</EmptyState>
      <Link to="/" className="text-sm font-semibold text-brand underline">
        Back to dashboard
      </Link>
    </div>
  )
}
