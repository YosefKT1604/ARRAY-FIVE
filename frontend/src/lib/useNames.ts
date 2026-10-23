import { useQuery } from '@tanstack/react-query'
import { formatDate } from './format'
import { listDependencies, listDeliveries, listJobs, listResources, listSuppliers } from '../api/endpoints'

export type EntityKind = 'supplier' | 'delivery' | 'resource' | 'job' | 'commitment'

export const KIND_LABEL: Record<EntityKind, string> = {
  supplier: 'Supplier',
  delivery: 'Delivery',
  resource: 'Item',
  job: 'Event',
  commitment: 'Commitment',
}

/**
 * Removes a bracketed ID whose name is already written earlier in the same clause, e.g. "Maju Rental Supplies (S-01)"
 * or "Tekno seminar (J-02) customer commitment (CM-02)". Otherwise humanize() would turn the ID into the name again.
 * `nameOf` gives the name an ID stands for (for a commitment: its event's name), or undefined if unknown.
 */
export function dropRepeatedIds(text: string, nameOf: (id: string) => string | undefined): string {
  return text.replace(/ \(((?:[A-Z]{1,3})-\d{2,4})\)/g, (match, id: string, offset: number) => {
    const name = nameOf(id)
    const clause = text.slice(0, offset).split(/[.;:]\s/).pop() ?? ''
    return name && clause.toLowerCase().includes(name.toLowerCase()) ? '' : match
  })
}

/** Turns entity IDs from the API into names people recognise. IDs stay opaque: types come from lookups. */
export function useNames() {
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: listJobs })
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers })
  const resources = useQuery({ queryKey: ['resources'], queryFn: listResources })
  const deliveries = useQuery({ queryKey: ['deliveries'], queryFn: listDeliveries })
  const dependencies = useQuery({ queryKey: ['dependencies'], queryFn: listDependencies })

  const job = (id: string) => jobs.data?.items.find((j) => j.id === id)
  const supplier = (id: string) => suppliers.data?.items.find((s) => s.id === id)
  const resource = (id: string) => resources.data?.items.find((r) => r.id === id)
  const delivery = (id: string) => deliveries.data?.items.find((d) => d.id === id)
  const commitmentJobId = (id: string) =>
    dependencies.data?.items.find((d) => d.dependency_type === 'fulfils' && d.target_id === id)?.source_id

  function kindOf(id: string, hint?: EntityKind): EntityKind | undefined {
    if (hint) return hint
    if (supplier(id)) return 'supplier'
    if (delivery(id)) return 'delivery'
    if (resource(id)) return 'resource'
    if (job(id)) return 'job'
    if (commitmentJobId(id)) return 'commitment'
    return undefined
  }

  function label(id: string, hint?: EntityKind, short = false): string {
    switch (kindOf(id, hint)) {
      case 'supplier': {
        const s = supplier(id)
        return s ? (short ? (s.aliases?.[0] ?? s.name) : s.name) : id
      }
      case 'delivery': {
        // "Maju's delivery (40 chairs, due Wed 21 Oct)": people know deliveries by who and what, not by ID.
        const d = delivery(id)
        const s = d && supplier(d.supplier_id)
        if (!d || !s) return `Delivery ${id}`
        const owner = `${s.aliases?.[0] ?? s.name}'s delivery`
        if (short) return owner
        const r = resource(d.resource_id)
        const what = r ? `${d.quantity} ${r.unit}${d.quantity === 1 ? '' : 's'}` : `${d.quantity} items`
        return `${owner} (${what}, due ${formatDate(d.expected_date)})`
      }
      case 'resource':
        return resource(id)?.name ?? id
      case 'job':
        return job(id)?.name ?? id
      case 'commitment': {
        const j = commitmentJobId(id)
        const name = j ? job(j)?.name : undefined
        return name ? `Commitment for ${name}` : `Commitment ${id}`
      }
      default:
        return id
    }
  }

  /**
   * Makes backend text readable: ISO dates -> "Thu 22 Oct", known entity IDs -> names.
   * Unknown IDs are left alone. Keep the raw text in a "Details" section.
   */
  function humanize(text: string): string {
    const nameOf = (id: string) => {
      const kind = kindOf(id)
      if (kind === 'commitment') {
        const j = commitmentJobId(id)
        return j ? job(j)?.name : undefined
      }
      return kind && kind !== 'delivery' ? label(id) : undefined
    }
    return dropRepeatedIds(text, nameOf)
      .replace(/\b\d{4}-\d{2}-\d{2}\b/g, (d) => formatDate(d))
      .replace(/\b(?:[A-Z]{1,3})-\d{2,4}\b/g, (id) => {
        const kind = kindOf(id)
        if (!kind) return id
        if (kind === 'commitment') return label(id).replace('Commitment for', 'the commitment for')
        return label(id)
      })
  }

  return { kindOf, label, humanize, resource, supplier, job, delivery, isLoading: jobs.isLoading || resources.isLoading }
}
