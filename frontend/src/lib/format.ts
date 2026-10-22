import { TIME_ZONE } from '../config'
import type { Money } from '../types/contracts'

/** Money -> "RM 80.00". null/undefined means unknown, which must never read as RM 0.00. */
export function formatMoney(money: Money | null | undefined): string {
  if (money == null) return 'Cost unknown'
  const prefix = money.currency === 'MYR' ? 'RM' : money.currency
  return `${prefix} ${money.amount}`
}

/** Timestamps without an offset are UTC from the backend; treat them as such. */
function parseTimestamp(value: string): Date {
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasOffset ? value : `${value}Z`)
}

/** Calendar dates ("2026-10-22") are business-timezone dates; pin them to noon KL so they never shift. */
function parseCalendarDate(value: string): Date {
  return new Date(`${value}T12:00:00+08:00`)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unknown date'
  return new Intl.DateTimeFormat('en-MY', {
    timeZone: TIME_ZONE,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(parseCalendarDate(value))
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unknown time'
  return new Intl.DateTimeFormat('en-MY', {
    timeZone: TIME_ZONE,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(parseTimestamp(value))
}
