import { cn } from '../lib/cn'
import { checkLabel } from '../lib/plans'
import { useNames } from '../lib/useNames'
import type { Check } from '../types/contracts'

const ICON = {
  pass: { icon: '✓', tone: 'text-ok', sr: 'Passed.' },
  fail: { icon: '✕', tone: 'text-bad', sr: 'Failed.' },
  unresolved: { icon: '?', tone: 'text-warn', sr: 'Not confirmed.' },
} as const

/** Validation checks in plain words. Codes and raw text live under "Details". */
export function CheckList({ checks }: { checks: Check[] }) {
  const names = useNames()
  if (checks.length === 0) return null
  return (
    <ul className="space-y-2">
      {checks.map((c, i) => {
        const s = ICON[c.result]
        return (
          <li key={`${c.code}-${i}`} className="flex gap-2.5 text-sm">
            <span className={cn('mt-0.5 w-4 shrink-0 text-center font-bold', s.tone)} aria-hidden>
              {s.icon}
            </span>
            <div>
              <p>
                <span className="font-semibold">{checkLabel(c.code, c.result)}.</span> <span className="sr-only">{s.sr}</span>
                {names.humanize(c.detail)}
              </p>
              <details className="mt-0.5 text-xs text-muted">
                <summary className="cursor-pointer">Details</summary>
                <p className="mt-1">
                  Code: {c.code} · Result: {c.result}
                </p>
                <p>Original: {c.detail}</p>
                {c.evidence_ids.length > 0 && <p>Evidence: {c.evidence_ids.join(', ')}</p>}
              </details>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
