import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import incidentFixture from '../../../fixtures/demo/incident.json'
import { listResources, listSuppliers, listWhatsAppInbox, sendWhatsAppMessage } from '../api/endpoints'
import { AiBadge } from '../components/AiBadge'
import { EmptyState, ErrorPanel, LoadingState } from '../components/states'
import { btnPrimary, btnSecondary, card, inputBase } from '../components/ui'
import { cn } from '../lib/cn'
import { formatDate, formatDateTime, formatTimeOfDay } from '../lib/format'
import type { IncomingMessage, Resource, Supplier } from '../types/contracts'

/** A sender who is not a saved supplier contact. Not offered in "Send as" for now; the backend still accepts it. */
const UNKNOWN = ''

/** Who sent a message, as the owner would recognise them. */
function senderLabel(message: IncomingMessage, suppliers: Supplier[]): string {
  const supplier = suppliers.find((s) => s.contact_reference && s.contact_reference === message.from_contact)
  return supplier?.name ?? message.contact_name ?? message.from_number ?? 'Unknown sender'
}

/** One line of what the message reading found, e.g. "Maju Rental Supplies · 20 Chair · new date Fri 23 Oct". */
function readingSummary(message: IncomingMessage, suppliers: Supplier[], resources: Resource[]): string {
  const d = message.extraction.draft_incident
  const parts = [
    suppliers.find((s) => s.id === d.supplier_id)?.name,
    d.quantity_affected != null || d.resource_id
      ? [d.quantity_affected, resources.find((r) => r.id === d.resource_id)?.name].filter((x) => x != null).join(' ')
      : undefined,
    d.new_arrival_date ? `new date ${formatDate(d.new_arrival_date)}` : undefined,
  ]
  return parts.filter(Boolean).join(' · ') || 'Nothing recognised yet'
}

function Bubble({ side, children, time }: { side: 'out' | 'in'; children: React.ReactNode; time?: string }) {
  return (
    <div className={cn('flex', side === 'out' ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-sm',
          side === 'out' ? 'rounded-br-sm bg-ok-bg text-ink' : 'rounded-bl-sm border border-line bg-card text-ink',
        )}
      >
        {children}
        {time && <span className="mt-1 block text-right text-xs text-muted">{time}</span>}
      </div>
    </div>
  )
}

export function WhatsAppSimulator() {
  const queryClient = useQueryClient()
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers })
  const resources = useQuery({ queryKey: ['resources'], queryFn: listResources })
  const inbox = useQuery({ queryKey: ['whatsapp-inbox'], queryFn: listWhatsAppInbox })

  const contacts = (suppliers.data?.items ?? []).filter((s) => s.contact_reference?.startsWith('whatsapp:'))
  const [sender, setSender] = useState<string | null>(null)
  const fromContact = sender ?? contacts[0]?.contact_reference ?? UNKNOWN
  const [number, setNumber] = useState('')
  const [savedName, setSavedName] = useState('')
  const [text, setText] = useState('')

  const send = useMutation({
    mutationFn: () =>
      sendWhatsAppMessage(
        fromContact === UNKNOWN
          ? { text, from_number: number.trim() || null, contact_name: savedName.trim() || null }
          : { text, from_contact: fromContact },
      ),
    onSuccess: () => {
      setText('')
      void queryClient.invalidateQueries({ queryKey: ['whatsapp-inbox'] })
      // A complete reading is filed as a disruption straight away, so the dashboard has news too.
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const items = inbox.data?.items ?? []
  // The phone shows only this sender's chat, oldest first, like WhatsApp does.
  const chat = items
    .filter((m) => (fromContact === UNKNOWN ? !m.from_contact && (m.from_number ?? '') === number.trim() : m.from_contact === fromContact))
    .reverse()
  const supplierList = suppliers.data?.items ?? []
  const resourceList = resources.data?.items ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">WhatsApp (simulated)</h1>
        <p className="mt-1 text-muted">
          Play a supplier sending a WhatsApp message to the business. Nothing goes to a real phone. Each message lands
          in the owner's inbox with what we read from it, and a complete one is reported straight away.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className={cn(card, 'flex flex-col')} aria-labelledby="phone">
          <h2 id="phone" className="text-lg font-semibold">
            Supplier's phone
          </h2>
          {suppliers.isLoading && <LoadingState label="Loading contacts…" />}
          {suppliers.error && <ErrorPanel error={suppliers.error} />}

          <label className="mt-3 block text-sm">
            <span className="font-semibold">Send as</span>
            <select
              value={fromContact}
              onChange={(e) => setSender(e.target.value)}
              className={cn(inputBase, 'mt-1 border-line')}
            >
              {contacts.map((s) => (
                <option key={s.id} value={s.contact_reference!}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {fromContact === UNKNOWN && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="font-semibold">Phone number</span>
                <input
                  value={number}
                  onChange={(e) => setNumber(e.target.value)}
                  placeholder="e.g. +60 12-345 6789"
                  className={cn(inputBase, 'mt-1 border-line')}
                />
              </label>
              <label className="block text-sm">
                <span className="font-semibold">Saved in owner's phone as (optional)</span>
                <input
                  value={savedName}
                  onChange={(e) => setSavedName(e.target.value)}
                  placeholder="e.g. Maju"
                  className={cn(inputBase, 'mt-1 border-line')}
                />
              </label>
            </div>
          )}

          <div className="mt-4 min-h-40 flex-1 space-y-2 rounded-xl bg-paper p-3" aria-label="Chat" role="log">
            {chat.length === 0 && <p className="py-6 text-center text-sm text-muted">No messages from this sender yet.</p>}
            {chat.map((m) => (
              <div key={m.id} className="space-y-2">
                <Bubble side="out" time={formatTimeOfDay(m.received_at)}>
                  {m.text}
                </Bubble>
                <Bubble side="in">
                  <span className="block text-xs font-semibold text-muted">Business (auto-reply)</span>
                  {m.reply}
                </Bubble>
              </div>
            ))}
          </div>

          <form
            className="mt-3 space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (text.trim()) send.mutate()
            }}
          >
            <textarea
              aria-label="Message"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              placeholder="Type a message…"
              className={cn(inputBase, 'border-line')}
            />
            <div className="flex flex-wrap gap-3">
              <button type="submit" className={btnPrimary} disabled={!text.trim() || send.isPending}>
                {send.isPending ? 'Sending…' : 'Send'}
              </button>
              <button
                type="button"
                className={btnSecondary}
                onClick={() => {
                  setSender(incidentFixture.supplier_message.from_contact)
                  setText(incidentFixture.supplier_message.text)
                }}
              >
                Use the demo message
              </button>
            </div>
            {send.error && <ErrorPanel error={send.error} />}
          </form>
        </section>

        <section className={card} aria-labelledby="inbox">
          <h2 id="inbox" className="text-lg font-semibold">
            Owner's inbox
          </h2>
          <p className="mt-1 text-sm text-muted">
            What we read from each message. When every detail is found, the problem is reported automatically; otherwise
            you check it first.
          </p>
          <div className="mt-3 space-y-3">
            {inbox.isLoading && <LoadingState label="Loading inbox…" />}
            {inbox.error && <ErrorPanel error={inbox.error} onRetry={() => void inbox.refetch()} />}
            {inbox.data && items.length === 0 && (
              <EmptyState title="No messages yet">Send one from the supplier's phone.</EmptyState>
            )}
            {items.length > 0 && (
              <ul className="space-y-3">
                {items.map((m) => (
                  <li key={m.id} className="rounded-xl border border-line p-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-semibold">{senderLabel(m, supplierList)}</span>
                      <span className="text-xs text-muted">{formatDateTime(m.received_at)}</span>
                    </div>
                    <p className="mt-1 text-sm">“{m.text}”</p>
                    <p className="mt-2 text-sm">
                      <span className="text-muted">We read: </span>
                      {readingSummary(m, supplierList, resourceList)} <AiBadge generatedBy={m.extraction.generated_by} />
                    </p>
                    {m.disruption_id ? (
                      <p className="mt-2 text-sm font-medium text-ok">
                        {m.report_outcome === 'duplicate' ? 'Already reported. ' : 'Reported automatically. '}
                        <Link to={`/disruptions/${m.disruption_id}/impact`} className="font-semibold text-brand underline">
                          See the problem
                        </Link>
                      </p>
                    ) : (
                      <>
                        {m.not_filed_reasons?.map((reason) => (
                          <p key={reason} className="mt-1 text-sm font-medium text-bad">
                            Not filed: {reason}
                          </p>
                        ))}
                        <p className="mt-1 text-sm font-medium text-warn">
                          {m.extraction.needs_clarification
                            ? "Some details are missing. You'll fill them in."
                            : 'Not reported yet. Check the details first.'}
                        </p>
                        <Link to={`/report?message=${m.id}`} className={cn(btnSecondary, 'mt-3')}>
                          Check and report
                        </Link>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Link to="/" className="mt-4 inline-block text-sm font-semibold text-brand underline">
            Back to dashboard
          </Link>
        </section>
      </div>
    </div>
  )
}
