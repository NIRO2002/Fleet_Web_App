import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { CheckCircle2, Pencil, Plus, RefreshCw, Trash2, Truck, X, XCircle } from 'lucide-react'
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
  VehicleTypeFieldsFieldset,
} from '../components/UI'
import { vehicleTypeService } from '../services/vehicleTypeService'
import type { VehicleTypeCatalog, VehicleTypeCatalogDraft } from '../types'
import { emptyVehicleTypeDraft, formatNumber, vehicleTypeDraftToInput, vehicleTypeToDraft } from '../utils/format'

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null

export function VehicleTypesPage() {
  const [vehicleTypes, setVehicleTypes] = useState<VehicleTypeCatalog[]>([])
  const [loading, setLoading] = useState(true)
  const [pageNotice, setPageNotice] = useState<Notice>(null)

  const [editingCode, setEditingCode] = useState<string | null>(null)
  const [draft, setDraft] = useState<VehicleTypeCatalogDraft>(() => emptyVehicleTypeDraft())
  const [submitting, setSubmitting] = useState(false)
  const [formNotice, setFormNotice] = useState<Notice>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const [deactivatingCode, setDeactivatingCode] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<'all' | 'ACTIVE' | 'INACTIVE'>('all')

  const refresh = async () => {
    setLoading(true)
    try {
      setVehicleTypes(await vehicleTypeService.list())
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

  const startEdit = (vehicleType: VehicleTypeCatalog) => {
    setEditingCode(vehicleType.code)
    setDraft(vehicleTypeToDraft(vehicleType))
    setFormNotice(null)
    setIsModalOpen(true)
  }

  const openAddModal = () => {
    setEditingCode(null)
    setDraft(emptyVehicleTypeDraft())
    setFormNotice(null)
    setIsModalOpen(true)
  }

  const cancelEdit = () => {
    setEditingCode(null)
    setDraft(emptyVehicleTypeDraft())
    setFormNotice(null)
    setIsModalOpen(false)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormNotice(null)
    try {
      const payload = vehicleTypeDraftToInput(draft)
      setSubmitting(true)
      if (editingCode !== null) {
        await vehicleTypeService.update(editingCode, payload)
        setFormNotice({ tone: 'success', text: `${payload.display_name} updated.` })
      } else {
        await vehicleTypeService.create(payload)
        setFormNotice({ tone: 'success', text: `${payload.display_name} added.` })
      }
      setEditingCode(null)
      setDraft(emptyVehicleTypeDraft())
      setIsModalOpen(false)
      await refresh()
    } catch (err) {
      setFormNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to save vehicle type.' })
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeactivate = async (vehicleType: VehicleTypeCatalog) => {
    if (!window.confirm(`Deactivate "${vehicleType.display_name}"? It will be hidden from new optimization runs but historical records stay intact.`)) return
    setDeactivatingCode(vehicleType.code)
    setPageNotice(null)
    try {
      await vehicleTypeService.deactivate(vehicleType.code)
      if (editingCode === vehicleType.code) cancelEdit()
      await refresh()
    } catch (err) {
      setPageNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to deactivate vehicle type.' })
    } finally {
      setDeactivatingCode(null)
    }
  }

  const filtered = useMemo(
    () =>
      statusFilter === 'all'
        ? vehicleTypes
        : vehicleTypes.filter((v) => (statusFilter === 'ACTIVE' ? v.is_active : !v.is_active)),
    [vehicleTypes, statusFilter],
  )

  const activeCount = vehicleTypes.filter((v) => v.is_active).length
  const inactiveCount = vehicleTypes.length - activeCount

  return (
    <div>
      <PageHeader
        action={
          <div className="flex items-center gap-2">
            <SecondaryButton onClick={refresh}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </SecondaryButton>
            <PrimaryButton onClick={openAddModal}>
              <Plus className="h-4 w-4" /> Add Vehicle Type
            </PrimaryButton>
          </div>
        }
        description="Manage the vehicle types (capacity, cost, cargo dimensions, availability) that NSGA-II optimizes against. This is the same catalog the optimizer reads from."
        title="Vehicle Types"
      />

      {pageNotice && (
        <div className="mb-5">
          <InlineAlert tone={pageNotice.tone}>{pageNotice.text}</InlineAlert>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={Truck} label="Total Vehicle Types" tone="blue" value={formatNumber(vehicleTypes.length)} />
        <MetricCard icon={CheckCircle2} label="Active" tone="green" value={formatNumber(activeCount)} />
        <MetricCard icon={XCircle} label="Inactive" tone="amber" value={formatNumber(inactiveCount)} />
      </div>

      {isModalOpen && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/60 p-4"
          onClick={cancelEdit}
        >
          <div
            className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-2xl bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-fleet-line/80 px-5 py-4">
              <h2 className="text-base font-extrabold text-fleet-ink">
                {editingCode !== null ? 'Edit Vehicle Type' : 'Add Vehicle Type'}
              </h2>
              <button
                aria-label="Close"
                className="focus-ring rounded-lg p-2 text-fleet-muted transition hover:bg-slate-100 hover:text-fleet-ink"
                onClick={cancelEdit}
                type="button"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5">
              {formNotice && (
                <div className="mb-4">
                  <InlineAlert tone={formNotice.tone}>{formNotice.text}</InlineAlert>
                </div>
              )}
              <form className="space-y-4" onSubmit={handleSubmit}>
                <VehicleTypeFieldsFieldset onChange={setDraft} value={draft} />
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-fleet-line/80 pt-4">
                  <span className="text-xs font-semibold text-fleet-muted">
                    Volume, weight, and speed feed directly into NSGA-II's objectives and constraints.
                  </span>
                  <div className="flex items-center gap-2">
                    <SecondaryButton onClick={cancelEdit}>Cancel</SecondaryButton>
                    <PrimaryButton loading={submitting} type="submit">
                      <Plus className="h-4 w-4" /> {editingCode !== null ? 'Update Vehicle Type' : 'Add Vehicle Type'}
                    </PrimaryButton>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

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
            {filtered.length} of {vehicleTypes.length} vehicle types shown
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
          <DataTable headers={['Code', 'Display Name', 'Category', 'Capacity', 'Cost', 'Status', 'Actions']}>
            {filtered.map((vehicleType) => (
              <tr className="transition hover:bg-blue-50/40" key={vehicleType.code}>
                <td className="px-5 py-4 font-black text-fleet-ink">{vehicleType.code}</td>
                <td className="px-5 py-4 text-fleet-muted">{vehicleType.display_name}</td>
                <td className="px-5 py-4 text-fleet-muted">{vehicleType.category ?? '-'}</td>
                <td className="px-5 py-4 font-semibold">
                  {vehicleType.capacity_kg} kg / {vehicleType.capacity_m3} m³
                </td>
                <td className="px-5 py-4 text-fleet-muted">
                  {formatNumber(vehicleType.fixed_cost)} + {formatNumber(vehicleType.cost_per_km)}/km
                </td>
                <td className="px-5 py-4">
                  <StatusBadge tone={vehicleType.is_active ? 'green' : 'slate'}>{vehicleType.is_active ? 'Active' : 'Inactive'}</StatusBadge>
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <button
                      aria-label={`Edit ${vehicleType.display_name}`}
                      className="focus-ring rounded-lg p-2 text-fleet-muted transition hover:bg-blue-50 hover:text-fleet-blue"
                      onClick={() => startEdit(vehicleType)}
                      type="button"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      aria-label={`Deactivate ${vehicleType.display_name}`}
                      className="focus-ring rounded-lg p-2 text-fleet-muted transition hover:bg-red-50 hover:text-red-600 disabled:pointer-events-none disabled:opacity-50"
                      disabled={deactivatingCode === vehicleType.code || !vehicleType.is_active}
                      onClick={() => handleDeactivate(vehicleType)}
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
