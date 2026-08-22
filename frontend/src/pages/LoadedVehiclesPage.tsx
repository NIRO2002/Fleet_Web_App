import { useEffect, useMemo, useState } from 'react'
import { Bike, Car, CheckCircle2, Container, PackageOpen, Sparkles, Truck, View } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card, EmptyState, InlineAlert, LoadingState, PageHeader, PrimaryButton, SecondaryButton, StatusBadge } from '../components/UI'
import { CargoBay3D } from '../components/CargoBay3D'
import { DEFAULT_DEPOT } from '../data/mockData'
import { optimizationService } from '../services/optimizationService'
import { parcelService } from '../services/parcelService'
import { ApiError } from '../services/api'
import type { LoadPlan, LoadPlanVehicle, VehicleType } from '../types'
import { formatKg, formatM3, formatNumber, formatPercent } from '../utils/format'
import { readSession, writeSession } from '../utils/sessionStore'

const VEHICLE_ICON: Record<VehicleType, LucideIcon> = {
  BIKE: Bike,
  APE_CARGO: Car,
  TVS_KING: Car,
  MICRO_VAN: Truck,
  VAN_MED: Truck,
  TRUCK_2T: Container,
  TRUCK_4T: Container,
}

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null

// Every real depot present in the sample dataset (D-CMB-001..003); the demo
// only ever runs against real data, never a synthetic depot.
const DEPOT_CHOICES = ['D-CMB-001', 'D-CMB-002', 'D-CMB-003']

export function LoadedVehiclesPage() {
  const [depotId, setDepotId] = useState(() => readSession('loadedVehicles.depotId', DEPOT_CHOICES[0]))
  // Real parcels are dated across the bundled dataset's own window, not "today" --
  // 2026-01-05 is the instance every depot in DEPOT_CHOICES has real parcels for.
  const [deliveryDate, setDeliveryDate] = useState(() => readSession('loadedVehicles.deliveryDate', '2026-01-05'))
  const [plan, setPlan] = useState<LoadPlan | null>(null)

  useEffect(() => {
    writeSession('loadedVehicles.depotId', depotId)
  }, [depotId])
  useEffect(() => {
    writeSession('loadedVehicles.deliveryDate', deliveryDate)
  }, [deliveryDate])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [notice, setNotice] = useState<Notice>(null)
  const [readyPending, setReadyPending] = useState<Set<string>>(new Set())
  const [viewingVehicle, setViewingVehicle] = useState<LoadPlanVehicle | null>(null)
  const [showParcelIds, setShowParcelIds] = useState(false)

  const loadExisting = async () => {
    setLoading(true)
    setNotice(null)
    try {
      setPlan(await optimizationService.findPlan(depotId, deliveryDate))
    } catch (err) {
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to load plan.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadExisting(), 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depotId, deliveryDate])

  useEffect(() => {
    if (!generating) return
    const interval = window.setInterval(() => setElapsedSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(interval)
  }, [generating])

  const handleGenerate = async () => {
    setElapsedSeconds(0)
    setGenerating(true)
    setNotice({ tone: 'info', text: 'Clustering parcels (HDBSCAN) then searching vehicle assignments (NSGA-II) - a 200-generation run can take several minutes.' })
    try {
      const parcels = await parcelService.listForInstance(depotId, deliveryDate)
      const parcelIds = parcels.map((p) => p.parcel_id)
      if (parcelIds.length === 0) {
        setNotice({ tone: 'error', text: `No parcels found for ${depotId} on ${deliveryDate}.` })
        return
      }
      await optimizationService.run({
        parcel_ids: parcelIds,
        depot_latitude: DEFAULT_DEPOT.latitude,
        depot_longitude: DEFAULT_DEPOT.longitude,
      })
      setNotice({ tone: 'success', text: `Load plan generated for ${parcelIds.length} parcels.` })
      await loadExisting()
    } catch (err) {
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Optimization run failed.' })
    } finally {
      setGenerating(false)
    }
  }

  const handleReady = async (vehicle: LoadPlanVehicle) => {
    setReadyPending((prev) => new Set(prev).add(vehicle.virtual_vehicle_id))
    // Optimistic update - the badge flips to READY immediately, then reverts if the server rejects it.
    setPlan((prev) => prev && {
      ...prev,
      vehicles: prev.vehicles.map((v) => v.virtual_vehicle_id === vehicle.virtual_vehicle_id ? { ...v, status: 'READY', ready_at: new Date().toISOString() } : v),
    })
    try {
      await optimizationService.markReady(vehicle.virtual_vehicle_id)
    } catch (err) {
      setPlan((prev) => prev && {
        ...prev,
        vehicles: prev.vehicles.map((v) => v.virtual_vehicle_id === vehicle.virtual_vehicle_id ? vehicle : v),
      })
      const text = err instanceof ApiError ? err.message : 'Failed to mark vehicle ready.'
      setNotice({ tone: 'error', text })
    } finally {
      setReadyPending((prev) => { const next = new Set(prev); next.delete(vehicle.virtual_vehicle_id); return next })
    }
  }

  const readyCount = useMemo(() => plan?.vehicles.filter((v) => v.status === 'READY').length ?? 0, [plan])

  return (
    <div>
      <PageHeader
        description="Vehicles are physically loaded, then marked READY for the fleet optimizer to collect."
        title="Loaded Vehicles"
      />

      <Card className="mb-5" title="Depot and date">
        <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto]">
          <label className="text-sm font-bold">
            Depot
            <select className="mt-1 block w-full rounded-xl border border-fleet-line px-3 py-2.5" onChange={(e) => setDepotId(e.target.value)} value={depotId}>
              {DEPOT_CHOICES.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </label>
          <label className="text-sm font-bold">
            Delivery date
            <input className="mt-1 block w-full rounded-xl border border-fleet-line px-3 py-2.5" onChange={(e) => setDeliveryDate(e.target.value)} type="date" value={deliveryDate} />
          </label>
          <div className="flex items-end">
            <PrimaryButton loading={generating} onClick={handleGenerate}>
              <Sparkles className="h-4 w-4" /> {generating ? `Optimizing… ${elapsedSeconds}s` : 'Generate Load Plan'}
            </PrimaryButton>
          </div>
        </div>
      </Card>

      {notice && <div className="mb-5"><InlineAlert tone={notice.tone}>{notice.text}</InlineAlert></div>}

      {loading ? (
        <LoadingState message="Checking for an existing load plan…" />
      ) : !plan ? (
        <EmptyState
          description={`No load plan for ${depotId} on ${deliveryDate}. Generate one above.`}
          icon={PackageOpen}
          title="No load plan for this date"
        />
      ) : (
        <>
          <div className="mb-5 grid gap-3 sm:grid-cols-4">
            <Summary label="Vehicles" value={formatNumber(plan.n_vehicles)} />
            <Summary label="Ready" value={`${readyCount} / ${plan.n_vehicles}`} />
            <Summary label="Mean utilization" value={formatPercent(plan.mean_utilization)} />
            <Summary label="Parcels" value={formatNumber(plan.n_parcels)} />
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {plan.vehicles.map((vehicle) => (
              <VehicleCard
                key={vehicle.virtual_vehicle_id}
                onReady={() => handleReady(vehicle)}
                onView3D={() => { setShowParcelIds(false); setViewingVehicle(vehicle) }}
                pending={readyPending.has(vehicle.virtual_vehicle_id)}
                vehicle={vehicle}
              />
            ))}
          </div>
        </>
      )}

      {viewingVehicle && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/60 p-4" onClick={() => setViewingVehicle(null)}>
          <div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl bg-white p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-extrabold text-fleet-ink">{viewingVehicle.virtual_vehicle_id}</h2>
                <p className="text-sm font-semibold text-fleet-muted">{viewingVehicle.parcel_count} parcels · {formatPercent(viewingVehicle.utilization)} utilization</p>
              </div>
              <div className="flex items-center gap-2">
                {viewingVehicle.status === 'READY' ? (
                  <StatusBadge tone="green">Ready{viewingVehicle.ready_at ? ` since ${new Date(viewingVehicle.ready_at).toLocaleTimeString()}` : ''}</StatusBadge>
                ) : (
                  <PrimaryButton loading={readyPending.has(viewingVehicle.virtual_vehicle_id)} onClick={() => { void handleReady(viewingVehicle); setViewingVehicle({ ...viewingVehicle, status: 'READY' }) }}>
                    <CheckCircle2 className="h-4 w-4" /> Ready
                  </PrimaryButton>
                )}
                <SecondaryButton onClick={() => setViewingVehicle(null)}>Close</SecondaryButton>
              </div>
            </div>
            <div className="mb-3 flex items-center justify-end">
              <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-fleet-ink">
                <span>Show Parcel IDs</span>
                <button
                  aria-checked={showParcelIds}
                  aria-label="Show Parcel IDs"
                  className={`relative h-6 w-11 rounded-full transition ${showParcelIds ? 'bg-blue-600' : 'bg-slate-300'}`}
                  onClick={() => setShowParcelIds((shown) => !shown)}
                  role="switch"
                  type="button"
                >
                  <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${showParcelIds ? 'translate-x-5' : ''}`} />
                </button>
              </label>
            </div>
            <CargoBay3D maxLoadSequence={viewingVehicle.parcels.length} mode="sequence" showParcelIds={showParcelIds} vehicle={viewingVehicle} />
          </div>
        </div>
      )}
    </div>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-fleet-line bg-white p-4 shadow-card">
      <div className="text-xs font-black uppercase tracking-wide text-fleet-muted">{label}</div>
      <div className="mt-1 truncate text-xl font-black">{value}</div>
    </div>
  )
}

function VehicleCard({ vehicle, onReady, onView3D, pending }: { vehicle: LoadPlanVehicle; onReady: () => void; onView3D: () => void; pending: boolean }) {
  const Icon = VEHICLE_ICON[vehicle.vehicle_type]
  const isReady = vehicle.status === 'READY'
  return (
    <div className="rounded-2xl border border-fleet-line bg-white p-5 shadow-card">
      <div className="mb-3 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-blue-50 text-blue-700"><Icon className="h-4 w-4" /></span>
          <div>
            <div className="font-black text-fleet-ink">{vehicle.virtual_vehicle_id}</div>
            <div className="text-xs font-bold text-fleet-muted">{vehicle.vehicle_type.replace('_', ' ')}</div>
          </div>
        </div>
        <StatusBadge tone={isReady ? 'green' : 'amber'}>{vehicle.status}</StatusBadge>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs font-bold uppercase text-fleet-muted">Parcels</div>
          <div className="font-extrabold">{vehicle.parcel_count}</div>
        </div>
        <div>
          <div className="text-xs font-bold uppercase text-fleet-muted">Utilization</div>
          <div className="font-extrabold">{formatPercent(vehicle.utilization)}</div>
        </div>
        <div>
          <div className="text-xs font-bold uppercase text-fleet-muted">Weight</div>
          <div className="font-extrabold">{formatKg(vehicle.used_weight_kg)}</div>
        </div>
        <div>
          <div className="text-xs font-bold uppercase text-fleet-muted">Volume</div>
          <div className="font-extrabold">{formatM3(vehicle.used_volume_m3)}</div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-fleet-line/80 pt-4">
        <SecondaryButton onClick={onView3D}>
          <View className="h-4 w-4" /> View 3D Load
        </SecondaryButton>
        {isReady ? (
          <span className="text-xs font-bold text-fleet-muted">{vehicle.ready_at ? `Ready at ${new Date(vehicle.ready_at).toLocaleTimeString()}` : 'Ready'}</span>
        ) : (
          <PrimaryButton loading={pending} onClick={onReady}>
            <CheckCircle2 className="h-4 w-4" /> Ready
          </PrimaryButton>
        )}
      </div>
    </div>
  )
}
