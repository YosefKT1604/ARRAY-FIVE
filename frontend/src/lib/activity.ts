import { USERS, type ActivityLogEntry } from '../types/contracts'

/** "U-01" -> "Nurul". The backend's own "system" actor reads as "SCDC". */
export function actorName(actorId: string): string {
  if (actorId === 'system') return 'SCDC'
  return USERS.find((u) => u.id === actorId)?.name ?? actorId
}

export interface ActivityContext {
  /** Plan summary by plan id, if known. */
  planTitle: (planId: string | null) => string | undefined
  /** Makes backend text readable (dates, entity names). */
  humanize: (text: string) => string
  disruptionDescription?: string
}

const trimDot = (t: string) => t.replace(/[.\s]+$/, '')

/** One log entry as a plain-language sentence. Raw type and details stay in the "Details" section. */
export function describeActivity(entry: ActivityLogEntry, ctx: ActivityContext): string {
  const who = actorName(entry.actor_id)
  const title = entry.plan_id ? ctx.planTitle(entry.plan_id) : undefined
  const plan = title ? `‘${trimDot(ctx.humanize(title))}’` : 'a plan'
  const d = entry.details
  const num = (v: unknown) => (typeof v === 'number' ? v : undefined)

  switch (entry.activity_type) {
    case 'disruption_reported':
      return ctx.disruptionDescription ? `Problem reported: ${trimDot(ctx.humanize(ctx.disruptionDescription))}.` : 'A problem was reported.'
    case 'disruption_extracted':
      return 'The supplier message was read to fill in the report.'
    case 'disruption_validated':
      return 'The report details were checked.'
    case 'analysis_completed': {
      const n = num(d.affected_count)
      return n === undefined ? 'We checked what this affects.' : `We checked what this affects: ${n} ${n === 1 ? 'item is' : 'items are'} affected.`
    }
    case 'plans_generated': {
      const n = Array.isArray(d.plan_ids) ? d.plan_ids.length : undefined
      return n === undefined ? 'Recovery options were prepared.' : `${n} recovery ${n === 1 ? 'option was' : 'options were'} prepared.`
    }
    case 'plan_edited':
      return `${who} edited ${plan} (version ${num(d.from_version) ?? '?'} → ${num(d.to_version) ?? '?'}).`
    case 'plan_revalidated':
      return `${plan} was checked again.`
    case 'plan_approved':
      return `${who} approved ${plan}.`
    case 'plan_rejected':
      return `${who} rejected ${plan}.`
    case 'info_requested':
      return `${who} asked for more information on ${plan}.`
    case 'approval_denied':
      return `${who} tried to approve or reject ${plan} but isn't allowed.`
    case 'draft_created':
      return `Draft messages were prepared for ${plan}. Nothing was sent.`
    case 'draft_approved':
      return `${who} approved a draft message. Nothing was sent.`
    case 'action_completed':
      return `${who} marked an action as done.`
    default:
      return String(entry.activity_type)
  }
}
