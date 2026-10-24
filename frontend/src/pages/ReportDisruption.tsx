import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import incidentFixture from '../../../fixtures/demo/incident.json'
import { ApiError } from '../api/errors'
import {
  analyzeDisruption,
  createDisruption,
  extractDisruption,
  listDeliveries,
  listResources,
  listSuppliers,
  listWhatsAppInbox,
} from '../api/endpoints'
import { AiBadge } from '../components/AiBadge'
import { ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary, btnSecondary, card, inputBase } from '../components/ui'
import { API_MODE } from '../config'
import { cn } from '../lib/cn'
import { formatDate } from '../lib/format'
import type { Delivery, DisruptionCreate, ExtractionResult } from '../types/contracts'

interface FormState {
  supplier_id: string
  resource_id: string
  delivery_id: string
  quantity_affected: string
  original_arrival_date: string
  new_arrival_date: string
  description: string
}

const EMPTY: FormState = {
  supplier_id: '',
  resource_id: '',
  delivery_id: '',
  quantity_affected: '',
  original_arrival_date: '',
  new_arrival_date: '',
  description: '',
}

// Material fields (CONTRACTS.md 6.1): without these the problem cannot be analysed.
const REQUIRED: (keyof FormState)[] = ['supplier_id', 'resource_id', 'quantity_affected', 'new_arrival_date']

const REQUIRED_MESSAGE: Partial<Record<keyof FormState, string>> = {
  supplier_id: 'Choose the supplier',
  resource_id: 'Choose what is affected',
  quantity_affected: 'Enter how many are affected (at least 1)',
  new_arrival_date: 'Enter the new arrival date',
}

/** "2026-10-21" -> "Wed 21 Oct" in free text. */
const plainDates = (text: string) => text.replace(/\b\d{4}-\d{2}-\d{2}\b/g, (d) => formatDate(d))

/** The extraction's evidence note in plain words: the sender's saved contact, dates by weekday. */
function plainEvidence(note: string): string {
  if (/sender contact/i.test(note)) return "from the sender's saved contact"
  return plainDates(note)
}

function prefill(result: ExtractionResult): FormState {
  const d = result.draft_incident
  return {
    supplier_id: d.supplier_id ?? '',
    resource_id: d.resource_id ?? '',
    delivery_id: d.delivery_id ?? '',
    quantity_affected: d.quantity_affected != null ? String(d.quantity_affected) : '',
    original_arrival_date: d.original_arrival_date ?? '',
    new_arrival_date: d.new_arrival_date ?? '',
    description: plainDates(d.description ?? ''),
  }
}

export function ReportDisruption() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers })
  const resources = useQuery({ queryKey: ['resources'], queryFn: listResources })
  const deliveries = useQuery({ queryKey: ['deliveries'], queryFn: listDeliveries })

  const [message, setMessage] = useState('')
  const [fromContact, setFromContact] = useState('')
  const [form, setForm] = useState<FormState>(EMPTY)
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null)
  const [clientErrors, setClientErrors] = useState<Partial<Record<keyof FormState, string>>>({})

  // Opened from the WhatsApp inbox (/report?message=WA-001): start from the reading stored when the message
  // arrived, so the message is not read again. The owner still checks every field before reporting.
  const [searchParams] = useSearchParams()
  const messageId = searchParams.get('message')
  const inbox = useQuery({ queryKey: ['whatsapp-inbox'], queryFn: listWhatsAppInbox, enabled: messageId != null })
  const inboxMessage = inbox.data?.items.find((m) => m.id === messageId)
  const [loadedMessageId, setLoadedMessageId] = useState<string | null>(null)
  if (inboxMessage && loadedMessageId !== inboxMessage.id) {
    setLoadedMessageId(inboxMessage.id)
    setMessage(inboxMessage.text)
    setFromContact(inboxMessage.from_contact ?? inboxMessage.contact_name ?? inboxMessage.from_number ?? '')
    setExtraction(inboxMessage.extraction)
    setForm(prefill(inboxMessage.extraction))
  }

  const extract = useMutation({
    mutationFn: (text: string) => extractDisruption(text, fromContact),
    onSuccess: (result) => {
      setExtraction(result)
      setForm(prefill(result))
      setClientErrors({})
    },
  })

  const submit = useMutation({
    mutationFn: async () => {
      const body: DisruptionCreate = {
        type: 'supplier_delay',
        source: extraction ? 'message' : 'form',
        supplier_id: form.supplier_id || null,
        resource_id: form.resource_id || null,
        delivery_id: form.delivery_id || null,
        quantity_affected: form.quantity_affected ? Number(form.quantity_affected) : null,
        original_arrival_date: form.original_arrival_date || null,
        new_arrival_date: form.new_arrival_date || null,
        description: form.description.trim() || 'Supplier delay',
        raw_message: extraction ? message : null,
      }
      const { disruption } = await createDisruption(body)
      try {
        await analyzeDisruption(disruption.id)
      } catch {
        /* The impact page offers "Check impact" if this step failed. */
      }
      return disruption
    },
    onSuccess: (disruption) => {
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['disruption', disruption.id] })
      void queryClient.invalidateQueries({ queryKey: ['impact', disruption.id] })
      navigate(`/disruptions/${disruption.id}/impact`)
    },
  })

  const unresolved = new Map((extraction?.unresolved_fields ?? []).map((u) => [u.field, u.note ?? 'Not found in the message.']))
  const serverErrors = submit.error instanceof ApiError ? submit.error.fieldErrors : {}

  const set = (field: keyof FormState, value: string) => {
    setForm((f) => {
      const next = { ...f, [field]: value }
      // Choosing a delivery fills in its original date, so people don't retype it.
      if (field === 'delivery_id' && value && !f.original_arrival_date) {
        const d = deliveries.data?.items.find((x) => x.id === value)
        if (d) next.original_arrival_date = d.expected_date
      }
      return next
    })
    setClientErrors((e) => ({ ...e, [field]: undefined }))
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const errors: Partial<Record<keyof FormState, string>> = {}
    for (const f of REQUIRED) {
      if (!form[f] || (f === 'quantity_affected' && Number(form[f]) < 1)) errors[f] = REQUIRED_MESSAGE[f]
    }
    setClientErrors(errors)
    if (Object.keys(errors).length === 0) submit.mutate()
  }

  function field(name: keyof FormState, label: string, input: (props: { id: string; className: string }) => ReactNode) {
    const flagged = unresolved.has(name) && !form[name]
    const error = clientErrors[name] ?? serverErrors[name]
    const evidence = extraction?.field_evidence[name]
    return (
      <div>
        <label htmlFor={name} className="mb-1 block text-sm font-semibold">
          {label}
          {REQUIRED.includes(name) && <span className="text-bad"> *</span>}
        </label>
        {input({
          id: name,
          className: cn(inputBase, error ? 'border-bad' : flagged ? 'border-warn bg-warn-bg/40' : 'border-line'),
        })}
        {error && (
          <p role="alert" className="mt-1 text-sm font-medium text-bad">
            {error}
          </p>
        )}
        {!error && flagged && <p className="mt-1 text-sm text-warn">{unresolved.get(name)} Please fill this in.</p>}
        {!error && !flagged && evidence && <p className="mt-1 text-xs text-muted">How we got this: {plainEvidence(evidence)}</p>}
      </div>
    )
  }

  // "Maju's delivery: 40 chairs, due Wed 21 Oct"
  function deliveryOption(d: Delivery): string {
    const s = suppliers.data?.items.find((x) => x.id === d.supplier_id)
    const unit = resources.data?.items.find((r) => r.id === d.resource_id)?.unit
    const what = unit ? `${d.quantity} ${unit}${d.quantity === 1 ? '' : 's'}` : `${d.quantity} items`
    return `${s ? `${s.aliases?.[0] ?? s.name}'s delivery` : 'Delivery'}: ${what}, due ${formatDate(d.expected_date)}`
  }

  const loadingLists = suppliers.isLoading || resources.isLoading || deliveries.isLoading
  const listError = suppliers.error ?? resources.error ?? deliveries.error
  const selectedResource = resources.data?.items.find((r) => r.id === form.resource_id)
  const duplicateId = submit.error instanceof ApiError ? submit.error.fieldErrors.existing_id : undefined

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Report a problem</h1>
        <p className="mt-1 text-muted">Tell us what went wrong. Nothing is sent to anyone.</p>
      </div>

      {messageId && inbox.isLoading && <LoadingState label="Loading the WhatsApp message…" />}
      {messageId && inbox.error && <ErrorPanel error={inbox.error} />}
      {messageId && inbox.data && !inboxMessage && (
        <p role="alert" className="rounded-xl bg-warn-bg p-3 text-sm text-warn">
          WhatsApp message {messageId} was not found. You can still fill in the form yourself.
        </p>
      )}
      {inboxMessage && (
        <p role="status" className="rounded-xl bg-info-bg p-3 text-sm">
          Filled in from WhatsApp message {inboxMessage.id}.{' '}
          <Link to="/whatsapp" className="font-semibold text-brand underline">
            Back to the inbox
          </Link>
        </p>
      )}

      <section className={card}>
        <h2 className="text-lg font-semibold">1. Paste the supplier's message (optional)</h2>
        <p className="mt-1 text-sm text-muted">We'll read it and fill in the form below. You check it before anything is saved.</p>
        <textarea
          aria-label="Supplier message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          placeholder="e.g. Boss, our chair delivery for tomorrow will be late…"
          className={cn(inputBase, 'mt-3 border-line')}
        />
        <label className="mt-3 block text-sm">
          <span className="font-semibold">Who sent it? (optional)</span>
          <input
            value={fromContact}
            onChange={(e) => setFromContact(e.target.value)}
            placeholder="e.g. a WhatsApp number or contact name"
            className={cn(inputBase, 'mt-1 border-line')}
          />
        </label>
        <div className="mt-3 flex flex-wrap gap-3">
          <button
            type="button"
            className={btnPrimary}
            disabled={!message.trim() || extract.isPending}
            onClick={() => extract.mutate(message)}
          >
            {extract.isPending ? 'Reading…' : 'Read message'}
          </button>
          <button
            type="button"
            className={btnSecondary}
            onClick={() => {
              setMessage(incidentFixture.supplier_message.text)
              setFromContact(incidentFixture.supplier_message.from_contact)
            }}
          >
            Use the demo message
          </button>
        </div>
        {extract.error && (
          <div className="mt-3">
            <ErrorPanel error={extract.error} />
          </div>
        )}
        {extraction && (
          <div className="mt-4 space-y-2 rounded-xl bg-info-bg p-3 text-sm" role="status">
            <p className="font-semibold">
              Message read. Check the details below.{' '}
              <AiBadge generatedBy={extraction.generated_by} />
            </p>
            {API_MODE === 'mock' && (
              <p className="text-muted">Mock mode: message reading is simulated with simple keyword rules.</p>
            )}
            {extraction.needs_clarification && (
              <div>
                <p className="font-semibold text-warn">We couldn't find everything:</p>
                <ul className="list-disc pl-5">
                  {extraction.clarification_questions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <form onSubmit={onSubmit} noValidate className={cn(card, 'space-y-4')}>
        <h2 className="text-lg font-semibold">2. Confirm the details</h2>
        {loadingLists && <LoadingState label="Loading suppliers and items…" />}
        {listError && <ErrorPanel error={listError} />}

        {field('supplier_id', 'Which supplier is late?', (p) => (
          <select {...p} value={form.supplier_id} onChange={(e) => set('supplier_id', e.target.value)}>
            <option value="">Choose…</option>
            {suppliers.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        ))}
        {field('resource_id', 'What is affected?', (p) => (
          <select {...p} value={form.resource_id} onChange={(e) => set('resource_id', e.target.value)}>
            <option value="">Choose…</option>
            {resources.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        ))}
        {field('delivery_id', 'Which order is delayed?', (p) => (
          <select {...p} value={form.delivery_id} onChange={(e) => set('delivery_id', e.target.value)}>
            <option value="">Not sure</option>
            {deliveries.data?.items
              .filter((d) => !form.supplier_id || d.supplier_id === form.supplier_id)
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {deliveryOption(d)}
                </option>
              ))}
          </select>
        ))}
        <div className="grid gap-4 sm:grid-cols-3">
          {field('quantity_affected', selectedResource ? `How many ${selectedResource.unit}s are delayed?` : 'How many are delayed?', (p) => (
            <input {...p} type="number" min={1} inputMode="numeric" value={form.quantity_affected} onChange={(e) => set('quantity_affected', e.target.value)} />
          ))}
          {field('original_arrival_date', 'Was due on', (p) => (
            <input {...p} type="date" value={form.original_arrival_date} onChange={(e) => set('original_arrival_date', e.target.value)} />
          ))}
          {field('new_arrival_date', 'Now arriving on', (p) => (
            <input {...p} type="date" value={form.new_arrival_date} onChange={(e) => set('new_arrival_date', e.target.value)} />
          ))}
        </div>
        {field('description', 'In your own words', (p) => (
          <textarea {...p} rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} />
        ))}

        {submit.error && (
          <div className="space-y-2">
            <ErrorPanel error={submit.error} />
            {duplicateId && (
              <Link to={`/disruptions/${duplicateId}/impact`} className="text-sm font-semibold text-brand underline">
                Open the existing report ({duplicateId})
              </Link>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className={btnPrimary} disabled={submit.isPending}>
            {submit.isPending ? 'Checking the impact…' : 'Report and check impact'}
          </button>
          <Link to="/" className="text-sm font-semibold text-brand underline">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}
