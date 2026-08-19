import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { CheckCircle2, Pencil, Plus, RefreshCw, Trash2, Truck, XCircle } from 'lucide-react'
import {
  Card,
  DataTable,
  EmptyState,
  InlineAlert,
  LoadingState,
  MetricCard,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  StatusBadge,
  VehicleCapabilityFieldsFieldset,
} from '../components/UI'
import { ApiError } from '../services/api'
import { vehicleCapabilityService } from '../services/vehicleCapabilityService'
import type { VehicleCapability, VehicleCapabilityDraft } from '../types'
import { emptyVehicleCapabilityDraft, formatNumber, vehicleCapabilityDraftToInput, vehicleCapabilityToDraft } from '../utils/format'

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null

export function VehicleTypesPage() {
  const [capabilities, setCapabilities] = useState<VehicleCapability[]>([])
  const [loading, setLoading] = useState(true)
  const [pageNotice, setPageNotice] = useState<Notice>(null)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState<VehicleCapabilityDraft>(() => emptyVehicleCapabilityDraft())
  const [submitting, setSubmitting] = useState(false)
  const [formNotice, setFormNotice] = useState<Notice>(null)

  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<'all' | 'ACTIVE' | 'INACTIVE'>('all')

  const refresh = async () => {
    setLoading(true)
    try {
      setCapabilities(await vehicleCapabilityService.list())
    } catch (err) {
      setPageNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to load vehicle types.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(timer)
  }, [])

  const startEdit = (capability: VehicleCapability) => {
    setEditingId(capability.id)
    setDraft(vehicleCapabilityToDraft(capability))
    setFormNotice(null)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setDraft(emptyVehicleCapabilityDraft())
    setFormNotice(null)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormNotice(null)
    try {
      const payload = vehicleCapabilityDraftToInput(draft)
      setSubmitting(true)
      if (editingId !== null) {
        await vehicleCapabilityService.update(editingId, payload)
        setFormNotice({ tone: 'success', text: `${payload.name} updated.` })
      } else {
        await vehicleCapabilityService.create(payload)
        setFormNotice({ tone: 'success', text: `${payload.name} added.` })
      }
      setEditingId(null)
      setDraft(emptyVehicleCapabilityDraft())
      await refresh()
    } catch (err) {
      setFormNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to save vehicle type.' })
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (capability: VehicleCapability) => {
    if (!window.confirm(`Delete "${capability.name}"? This cannot be undone.`)) return
    setDeletingId(capability.id)
    setPageNotice(null)
    try {
      await vehicleCapabilityService.remove(capability.id)
      if (editingId === capability.id) cancelEdit()
      await refresh()
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 409
          ? 'This vehicle type is currently assigned to registered vehicles and cannot be deleted.'
          : err instanceof Error
            ? err.message
            : 'Failed to delete vehicle type.'
      setPageNotice({ tone: 'error', text })
    } finally {
      setDeletingId(null)
    }
  }

  const filtered = useMemo(
    () => (statusFilter === 'all' ? capabilities : capabilities.filter((c) => c.status === statusFilter)),
    [capabilities, statusFilter],
  )

  const activeCount = capabilities.filter((c) => c.status === 'ACTIVE').length
  const inactiveCount = capabilities.length - activeCount

  return (
    <div>
      <PageHeader
        action={
          <SecondaryButton onClick={refresh}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </SecondaryButton>
        }
        description="Define vehicle capability types (e.g. Bajaj Three Wheeler) the optimizer can plan around. These are not physical vehicles — registered vehicles will reference a type."
        title="Vehicle Types"
      />

      {pageNotice && (
        <div className="mb-5">
          <InlineAlert tone={pageNotice.tone}>{pageNotice.text}</InlineAlert>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={Truck} label="Total Vehicle Types" tone="blue" value={formatNumber(capabilities.length)} />
        <MetricCard icon={CheckCircle2} label="Active" tone="green" value={formatNumber(activeCount)} />
        <MetricCard icon={XCircle} label="Inactive" tone="amber" value={formatNumber(inactiveCount)} />
      </div>

      <div className="mt-5">
        <Card title={editingId !== null ? 'Edit Vehicle Type' : 'Add Vehicle Type'}>
          {formNotice && (
            <div className="mb-4">
              <InlineAlert tone={formNotice.tone}>{formNotice.text}</InlineAlert>
            </div>
          )}
          <form className="space-y-4" onSubmit={handleSubmit}>
            <VehicleCapabilityFieldsFieldset onChange={setDraft} value={draft} />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-fleet-line/80 pt-4">
              <span className="text-xs font-semibold text-fleet-muted">
                Volume is calculated automatically from length × width × height.
              </span>
              <div className="flex items-center gap-2">
                {editingId !== null && <SecondaryButton onClick={cancelEdit}>Cancel</SecondaryButton>}
                <PrimaryButton loading={submitting} type="submit">
                  <Plus className="h-4 w-4" /> {editingId !== null ? 'Update Vehicle Type' : 'Add Vehicle Type'}
                </PrimaryButton>
              </div>
            </div>
          </form>
        </Card>
      </div>

      <div className="mt-5 rounded-2xl border border-fleet-line bg-white p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <select
            className="rounded-xl border border-fleet-line px-3 py-2 text-sm font-bold"
            onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
            value={statusFilter}
          >
            <option value="all">All Statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
          <span className="ml-auto text-sm font-bold text-fleet-muted">
            {filtered.length} of {capabilities.length} vehicle types shown
          </span>
        </div>
      </div>

      <div className="mt-4">
        {loading ? (
          <Card>
            <LoadingState message="Please wait while vehicle types are loading…" />
          </Card>
        ) : filtered.length === 0 ? (
          <EmptyState
            description="Add a vehicle type above to make it available to the optimizer."
            icon={Truck}
            title="No vehicle types match this filter"
          />
        ) : (
          <DataTable headers={['Name', 'Category', 'Brand / Model', 'Max Weight', 'Dimensions (L×W×H)', 'Volume', 'Status', 'Actions']}>
            {filtered.map((capability) => (
              <tr className="transition hover:bg-blue-50/40" key={capability.id}>
                <td className="px-5 py-4 font-black text-fleet-ink">{capability.name}</td>
                <td className="px-5 py-4 text-fleet-muted">{capability.category}</td>
                <td className="px-5 py-4 text-fleet-muted">
                  {[capability.brand, capability.model].filter(Boolean).join(' ') || '—'}
                </td>
                <td className="px-5 py-4 font-semibold">{capability.max_weight_kg} kg</td>
                <td className="px-5 py-4 text-fleet-muted">
                  {capability.max_length_cm} × {capability.max_width_cm} × {capability.max_height_cm} cm
                </td>
                <td className="px-5 py-4 font-semibold">{capability.max_volume_m3.toFixed(3)} m³</td>
                <td className="px-5 py-4">
                  <StatusBadge tone={capability.status === 'ACTIVE' ? 'green' : 'slate'}>{capability.status}</StatusBadge>
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <button
                      aria-label={`Edit ${capability.name}`}
                      className="focus-ring rounded-lg p-2 text-fleet-muted transition hover:bg-blue-50 hover:text-fleet-blue"
                      onClick={() => startEdit(capability)}
                      type="button"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      aria-label={`Delete ${capability.name}`}
                      className="focus-ring rounded-lg p-2 text-fleet-muted transition hover:bg-red-50 hover:text-red-600 disabled:pointer-events-none disabled:opacity-50"
                      disabled={deletingId === capability.id}
                      onClick={() => handleDelete(capability)}
                      type="button"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </div>
    </div>
  )
}
