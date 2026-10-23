// Friendly aliases over the generated backend types, plus types for endpoints the
// backend has not built yet (those follow docs/CONTRACTS.md). JSON keys stay snake_case.
import type { components } from './api.generated'

type S = components['schemas']

export type Money = S['Money']
export type Job = S['Job']
export type Supplier = S['SupplierWithOfferings']
export type Resource = S['Resource']
export type Delivery = S['Delivery']
export type Dependency = S['Dependency']
export type Disruption = S['DisruptionOut']
export type DisruptionCreate = S['DisruptionCreate']
export type DisruptionCreated = S['DisruptionCreated']
export type Incident = S['NormalizedIncident']
export type UnresolvedField = S['UnresolvedField']
export type ImpactResult = S['ImpactResult']
export type AffectedEntity = S['AffectedEntity']
export type RecoveryPlan = S['RecoveryPlan']
export type RecoveryAction = S['RecoveryAction']
export type ValidationResult = S['ValidationResult']
export type Check = S['Check']
export type Approval = S['ApprovalOut']
export type DecisionRequest = S['DecisionRequest']

export type ValidationStatus = ValidationResult['status']
export type CheckCode = S['CheckCode']
export type CheckResult = Check['result']
export type DisruptionStatus = S['DisruptionStatus']
export type PlanStatus = S['PlanStatus']

export type UserId = 'U-01' | 'U-02'
export const USERS: { id: UserId; name: string; role: 'owner' | 'staff' }[] = [
  { id: 'U-01', name: 'Nurul', role: 'owner' },
  { id: 'U-02', name: 'Hafiz', role: 'staff' },
]

// ---- Not built by the backend yet (CONTRACTS.md sections 6.2, 6.6, 6.7, 7) ----

export interface ExtractionResult {
  schema_version: '1.0'
  draft_incident: Omit<Incident, 'id' | 'reported_at'> & { reported_at?: string }
  field_evidence: Record<string, string>
  unresolved_fields: UnresolvedField[]
  needs_clarification: boolean
  clarification_questions: string[]
  generated_by: string
  fallback_used: boolean
  warnings: string[]
}

/** POST /whatsapp/messages body: a message as the chat app delivers it (P5, branch `integration`). */
export interface IncomingMessageCreate {
  text: string
  from_number?: string | null
  /** The name the owner saved for the number in their own phone (not the sender's profile name). */
  contact_name?: string | null
  /** Matched against Supplier.contact_reference, e.g. "whatsapp:maju-rental (synthetic)". */
  from_contact?: string | null
}

/** A stored WhatsApp message with the AI module's reading of it, made once on arrival. */
export interface IncomingMessage {
  id: string
  channel: string
  received_at: string
  text: string
  from_number: string | null
  contact_name: string | null
  from_contact: string | null
  extraction: ExtractionResult
  /** The disruption a complete reading was filed as automatically ("filed"), or the open one it repeats
   *  ("duplicate"). null = the message waits for the owner to check it. */
  disruption_id: string | null
  report_outcome: 'filed' | 'duplicate' | null
  /** The fixed acknowledgement the sender gets back; never AI text. */
  reply: string
}

export interface PlanComparison {
  plan_id: string
  validation_status: ValidationStatus
  benefits: string[]
  limitations: string[]
}

export interface Explanation {
  schema_version: '1.0'
  disruption_id: string
  summary: string
  impact_explanations: { entity_id: string; text: string }[]
  plan_comparisons: PlanComparison[]
  missing_confirmations: string[]
  next_steps: string[]
  generated_by: string
  fallback_used: boolean
  unsupported_claims_removed: number
}

export interface DraftMessage {
  id: string
  plan_id: string
  recipient_type: 'supplier' | 'customer'
  recipient_id: string
  body: string
  placeholders: string[]
  status: 'draft' | 'approved'
  generated_by: string
}

export type ActivityLogEntry = S['ActivityLogOut']
export type ActivityType = S['ActivityType']

export interface PlanEditRequest {
  base_version: number
  actions: RecoveryAction[]
  assumptions: string[]
}

/** One disruption that is waiting for a decision, with all its proposed plans. */
export interface PendingDecision {
  disruption: Disruption
  plans: RecoveryPlan[]
  /** The plan the API ranked first among those that are not infeasible (we never compute rank). */
  recommended: RecoveryPlan | null
}

/** Composed in the browser: the backend has no GET /dashboard yet. */
export interface Dashboard {
  upcoming_jobs: Job[]
  active_disruptions: Disruption[]
  pending_decisions: PendingDecision[]
}

// ---- Errors ----

/** The backend's ErrorCode enum (app/errors.py), matching CONTRACTS.md section 8 (401 is UNAUTHORIZED). */
export type ErrorCode =
  | 'BAD_REQUEST'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'DUPLICATE_DISRUPTION'
  | 'STALE_PLAN_VERSION'
  | 'PLAN_INFEASIBLE'
  | 'INVALID_STATE_TRANSITION'
  | 'VALIDATION_ERROR'
  | 'INTERNAL_ERROR'
