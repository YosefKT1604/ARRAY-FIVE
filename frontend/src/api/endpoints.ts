import { DEMO_TODAY } from '../config'
import { request } from './client'
import type {
  ActivityLogEntry,
  Approval,
  Dashboard,
  DecisionRequest,
  Delivery,
  Dependency,
  Disruption,
  DisruptionCreate,
  DisruptionCreated,
  DraftMessage,
  Explanation,
  ExtractionResult,
  ImpactResult,
  Job,
  PendingDecision,
  PlanEditRequest,
  RecoveryPlan,
  Resource,
  Supplier,
} from '../types/contracts'

type Items<T> = { items: T[] }

// ---- Built by the backend ----
export const getHealth = () => request<{ status: string }>('GET', '/health')
export const listJobs = () => request<Items<Job>>('GET', '/jobs')
export const listSuppliers = () => request<Items<Supplier>>('GET', '/suppliers')
export const listResources = () => request<Items<Resource>>('GET', '/resources')
export const listDeliveries = () => request<Items<Delivery>>('GET', '/deliveries')
export const listDependencies = () => request<Items<Dependency>>('GET', '/dependencies')

export const listDisruptions = () => request<Items<Disruption>>('GET', '/disruptions')
export const getDisruption = (id: string) => request<Disruption>('GET', `/disruptions/${id}`)
export const createDisruption = (body: DisruptionCreate) => request<DisruptionCreated>('POST', '/disruptions', body)
export const analyzeDisruption = (id: string) => request<ImpactResult>('POST', `/disruptions/${id}/analyze`)
export const getImpact = (id: string) => request<ImpactResult>('GET', `/disruptions/${id}/impact`)
export const generatePlans = (id: string) => request<Items<RecoveryPlan>>('POST', `/disruptions/${id}/recovery-plans`)
export const listPlans = (id: string) => request<Items<RecoveryPlan>>('GET', `/disruptions/${id}/recovery-plans`)
export const getPlan = (id: string) => request<RecoveryPlan>('GET', `/recovery-plans/${id}`)
export const approvePlan = (id: string, body: DecisionRequest) =>
  request<Approval>('POST', `/recovery-plans/${id}/approve`, body)
export const rejectPlan = (id: string, body: DecisionRequest) =>
  request<Approval>('POST', `/recovery-plans/${id}/reject`, body)

// ---- Not built yet: answered by MSW in hybrid mode (see mocks/missing-endpoints.ts) ----
export const extractDisruption = (message: string, from_contact?: string) =>
  request<ExtractionResult>('POST', '/disruptions/extract', { message, from_contact: from_contact || null })
export const getExplanation = (id: string) => request<Explanation>('GET', `/disruptions/${id}/explanation`)
export const editPlan = (id: string, body: PlanEditRequest) => request<RecoveryPlan>('PUT', `/recovery-plans/${id}`, body)
export const revalidatePlan = (id: string) => request<RecoveryPlan>('POST', `/recovery-plans/${id}/revalidate`)
export const requestInfo = (id: string, body: DecisionRequest) =>
  request<Approval>('POST', `/recovery-plans/${id}/request-info`, body)
export const createDrafts = (planId: string) => request<Items<DraftMessage>>('POST', `/recovery-plans/${planId}/drafts`)
export const approveDraft = (id: string) => request<DraftMessage>('POST', `/drafts/${id}/approve`)
export const getActivityLog = (id: string) => request<Items<ActivityLogEntry>>('GET', `/disruptions/${id}/activity-log`)

/** GET /dashboard does not exist on the backend, so the home screen is composed here. */
export async function getDashboard(): Promise<Dashboard> {
  const [jobs, disruptions] = await Promise.all([listJobs(), listDisruptions()])
  const active = disruptions.items.filter((d) => d.status !== 'closed')
  const awaiting = active.filter((d) => d.status === 'plans_ready')
  const planLists = await Promise.all(awaiting.map((d) => listPlans(d.id)))

  const pending_decisions = awaiting.flatMap((disruption, i): PendingDecision[] => {
    const plans = planLists[i].items.filter((p) => p.status === 'proposed')
    // Infeasible plans are not "waiting": nobody can approve them.
    const options = plans.filter((p) => p.validation?.status !== 'infeasible')
    if (options.length === 0) return []
    const ranked = options.filter((p) => p.rank != null).sort((a, b) => a.rank! - b.rank!)
    return [{ disruption, plans, recommended: ranked[0] ?? options[0] }]
  })

  const upcoming_jobs = jobs.items
    .filter((j) => j.event_date >= DEMO_TODAY)
    .sort((a, b) => a.event_date.localeCompare(b.event_date))
  return { upcoming_jobs, active_disruptions: active, pending_decisions }
}
