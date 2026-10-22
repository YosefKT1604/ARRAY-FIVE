import type { Check, CheckCode, RecoveryAction, RecoveryPlan } from '../types/contracts'

export const CHECK_LABEL: Record<CheckCode, string> = {
  RESOURCE_AVAILABLE: 'Item is available',
  QUANTITY_SUFFICIENT: 'Enough quantity',
  SUPPLIER_AVAILABLE: 'Supplier can provide it',
  LEAD_TIME_OK: 'Lead time is OK',
  DEADLINE_MET: 'Arrives in time',
  NO_DOUBLE_BOOKING: 'No double booking',
  DEPENDENCY_ORDER_OK: 'Steps are in the right order',
  COMMITMENT_RESCHEDULABLE: 'Commitment can be moved',
  FACTS_KNOWN: 'All facts are confirmed',
}

// Failing checks read better in the negative ("Arrives too late", not "Arrives in time" with a cross).
const CHECK_FAIL_LABEL: Record<CheckCode, string> = {
  RESOURCE_AVAILABLE: "Item isn't available",
  QUANTITY_SUFFICIENT: 'Not enough quantity',
  SUPPLIER_AVAILABLE: "Supplier can't provide it",
  LEAD_TIME_OK: 'Lead time is too long',
  DEADLINE_MET: 'Arrives too late',
  NO_DOUBLE_BOOKING: 'Double booking',
  DEPENDENCY_ORDER_OK: 'Steps are in the wrong order',
  COMMITMENT_RESCHEDULABLE: "Commitment can't be moved",
  FACTS_KNOWN: "Some facts aren't known",
}

export function checkLabel(code: string, result: 'pass' | 'fail' | 'unresolved' = 'pass'): string {
  const c = code as CheckCode
  if (result === 'fail') return CHECK_FAIL_LABEL[c] ?? code
  if (result === 'unresolved') {
    if (c === 'FACTS_KNOWN') return "Some facts aren't confirmed"
    const label = CHECK_LABEL[c] ?? code
    return `Not confirmed: ${label.charAt(0).toLowerCase()}${label.slice(1)}`
  }
  return CHECK_LABEL[c] ?? code
}

/** Display order only: by the API's own rank, unranked last. We never compute rank. */
export function sortByRank(plans: RecoveryPlan[]): RecoveryPlan[] {
  return [...plans].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity))
}

export const failingChecks = (plan: RecoveryPlan): Check[] => plan.validation?.checks.filter((c) => c.result === 'fail') ?? []
export const unresolvedChecks = (plan: RecoveryPlan): Check[] =>
  plan.validation?.checks.filter((c) => c.result === 'unresolved') ?? []

/** Assumptions the owner still has to confirm: the validator's list plus the plan's own. */
export function openQuestions(plan: RecoveryPlan): string[] {
  return [...new Set([...(plan.validation?.unresolved_assumptions ?? []), ...plan.assumptions])]
}

const normalise = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/**
 * The open questions for the owner, each once. These are the plan's assumptions (the things that
 * must be true). The explanations of unresolved checks live in "How it was checked", so they are
 * only used here when a plan lists no assumptions at all.
 */
export function stillToConfirm(plan: RecoveryPlan): string[] {
  const questions = openQuestions(plan)
  const source = questions.length > 0 ? questions : unresolvedChecks(plan).map((c) => c.detail)
  const seen = new Set<string>()
  return source.filter((q) => {
    const key = normalise(q)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

const DATE_WORDS = /(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/g

/**
 * Benefits must never include a fact that makes a check fail (for example "Arrives Fri 23 Oct"
 * on a plan that fails because it arrives too late). Works on humanized text.
 */
export function safeBenefits(benefits: string[], plan: RecoveryPlan, humanize: (t: string) => string): string[] {
  const failingText = failingChecks(plan).map((c) => humanize(c.detail))
  return benefits.filter((b) => {
    const dates = humanize(b).match(DATE_WORDS) ?? []
    return !dates.some((d) => failingText.some((f) => f.includes(d)))
  })
}

/** A plan edited by the demo-only mock (not by the backend). */
export const isDemoEdit = (plan: RecoveryPlan): boolean => plan.created_by === 'user_edit'

type Names = { label: (id: string, hint?: 'supplier' | 'resource' | 'job') => string }

/** One action in plain words. Parameter shapes are in CONTRACTS.md section 6.4. */
export function describeAction(action: RecoveryAction, names: Names, formatDate: (d: string) => string): string {
  const p = action.parameters as Record<string, unknown>
  const str = (k: string) => (typeof p[k] === 'string' ? (p[k] as string) : undefined)
  const qty = typeof p.quantity === 'number' ? p.quantity : undefined
  const res = str('resource_id') ? names.label(str('resource_id')!, 'resource') : 'items'
  const sup = str('supplier_id') ? names.label(str('supplier_id')!, 'supplier') : 'the supplier'
  switch (action.action_type) {
    case 'source_alternative_supplier': {
      const date = str('expected_arrival_date')
      return `Order ${qty ?? '?'} × ${res} from ${sup}${date ? `, arriving ${formatDate(date)}` : ''}`
    }
    case 'contact_supplier': {
      const date = str('requested_date')
      return `Ask ${sup}: ${str('request') ?? 'please confirm'}${date ? ` (by ${formatDate(date)})` : ''}`
    }
    case 'use_spare_inventory':
      return `Use ${qty ?? '?'} spare ${res}`
    case 'reallocate_resource':
      return `Move ${qty ?? '?'} × ${res} from ${str('from_job_id') ? names.label(str('from_job_id')!, 'job') : 'one event'} to ${str('to_job_id') ? names.label(str('to_job_id')!, 'job') : 'another'}`
    case 'reschedule_job':
      return `Move ${str('job_id') ? names.label(str('job_id')!, 'job') : 'the event'}${str('new_date') ? ` to ${formatDate(str('new_date')!)}` : ''}`
    case 'split_allocation':
      return `Split ${res} between events`
    default:
      return action.action_type
  }
}
