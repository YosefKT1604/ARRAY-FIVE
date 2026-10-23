import { formatMoney } from '../lib/format'
import type { Money } from '../types/contracts'

/** "RM 80.00", or "Cost unknown" for null. Never RM 0.00 for unknown. */
export function MoneyText({ value }: { value: Money | null | undefined }) {
  return <span className={value == null ? 'text-muted italic' : 'tabular-nums'}>{formatMoney(value)}</span>
}
