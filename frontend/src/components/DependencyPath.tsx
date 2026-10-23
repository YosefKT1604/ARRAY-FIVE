import { KIND_LABEL, useNames } from '../lib/useNames'

/** Shows how the problem travels, e.g. Maju → Delivery DL-01 → Folding Chairs → Wedding. */
export function DependencyPath({ path }: { path: string[] }) {
  const names = useNames()
  if (path.length === 0) return null
  return (
    <ol className="flex flex-wrap items-stretch gap-1.5" aria-label="How this problem reaches this item">
      {path.map((id, i) => {
        const kind = names.kindOf(id)
        return (
          <li key={`${id}-${i}`} className="flex items-stretch gap-1.5">
            {i > 0 && (
              <span aria-hidden className="flex items-center text-muted">
                →
              </span>
            )}
            <span className="rounded-lg border border-line bg-paper px-2.5 py-1 text-sm">
              {kind && <span className="block text-[10px] font-semibold tracking-wide text-muted uppercase">{KIND_LABEL[kind]}</span>}
              <span className="font-medium">{names.label(id, undefined, true)}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
