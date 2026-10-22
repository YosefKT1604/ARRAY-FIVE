import { DEMO_TODAY, TIME_ZONE } from '../config'
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

function dateParts(d: Date, extra: Intl.DateTimeFormatOptions = {}) {
  const parts = new Intl.DateTimeFormat('en-MY', {
    timeZone: TIME_ZONE,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...extra,
  }).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return { weekday: get('weekday'), day: get('day'), month: get('month'), parts }
}

/** "2026-10-22" -> "Thu 22 Oct" */
export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unknown date'
  const { weekday, day, month } = dateParts(parseCalendarDate(value))
  return `${weekday} ${day} ${month}`
}

/** Whole days from the demo date to `value` (negative = past). */
export function daysFromDemoToday(value: string): number {
  const ms = parseCalendarDate(value).getTime() - parseCalendarDate(DEMO_TODAY).getTime()
  return Math.round(ms / 86_400_000)
}

/** "today", "tomorrow", "in 2 days", "3 days ago", measured from the demo date. */
export function relativeDay(value: string): string {
  const n = daysFromDemoToday(value)
  if (n === 0) return 'today'
  if (n === 1) return 'tomorrow'
  if (n === -1) return 'yesterday'
  return n > 0 ? `in ${n} days` : `${-n} days ago`
}

/** "5 min ago" for a real timestamp (reported_at is real wall-clock time). */
export function relativeTime(value: string, now: number = Date.now()): string {
  const mins = Math.floor((now - parseTimestamp(value).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
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
