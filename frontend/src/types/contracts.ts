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

export interface ActivityLogEntry {
  id: string
  disruption_id: string
  actor_id: string
  activity_type: string
  details: Record<string, unknown>
  created_at: string
}

export interface PlanEditRequest {
  base_version: number
  actions: RecoveryAction[]
  assumptions: string[]
}

/** Composed in the browser: the backend has no GET /dashboard yet. */
export interface Dashboard {
  upcoming_jobs: Job[]
  active_disruptions: Disruption[]
  pending_approvals: { disruption: Disruption; plan: RecoveryPlan }[]
}

// ---- Errors ----

export type ErrorCode =
  | 'BAD_REQUEST'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'DUPLICATE_DISRUPTION'
  | 'STALE_PLAN_VERSION'
  | 'PLAN_INFEASIBLE'
  | 'INVALID_STATE_TRANSITION'
  | 'VALIDATION_ERROR'
  | 'INTERNAL_ERROR'
