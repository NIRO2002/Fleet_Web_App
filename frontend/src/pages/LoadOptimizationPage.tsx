import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import clsx from 'clsx'
import { Bike, Car, Container, Gauge, ListChecks, MapPin, PackageSearch, RefreshCw, Route, Sparkles, Truck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import {
  Card,
  CapacityBar,
  DataTable,
  EmptyState,
  InlineAlert,
  LoadingState,
  LabeledInput,
  MetricCard,
  PageHeader,
  ParcelFieldsFieldset,
  PrimaryButton,
  SecondaryButton,
  StatusBadge,
} from '../components/UI'
import { DEFAULT_DEPOT, VEHICLE_CATALOG } from '../data/mockData'
import { optimizationService } from '../services/optimizationService'
import { parcelService } from '../services/parcelService'
import type {
  ClusterSummary,
  OptimizationResult,
  OptimizationRunRequest,
  ParcelDraft,
  VehicleOption,
  VehicleType,
  VirtualVehicle,
} from '../types'
import {
  clusterLabel,
  emptyParcelDraft,
  formatDateTime,
  formatNumber,
  formatPercent,
  parcelDraftToInput,
  parseClusterKey,
  parseIdList,
  vehicleToneClass,
} from '../utils/format'

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null

interface NavState {
  parcelIds?: string[]
  clusterId?: number
}

const VEHICLE_ICON: Record<VehicleType, LucideIcon> = {
  BIKE: Bike,
  APE_CARGO: Car,
  TVS_KING: Car,
  MICRO_VAN: Truck,
  VAN_MED: Truck,
  TRUCK_2T: Container,
  TRUCK_4T: Container,
}

export function LoadOptimizationPage() {
  const location = useLocation()
  const navState = (location.state as NavState | null) ?? null

  const [mode, setMode] = useState<'cluster' | 'parcels'>(
    navState?.parcelIds && navState.parcelIds.length > 0 ? 'parcels' : 'cluster',
  )
  const [clusterSummary, setClusterSummary] = useState<ClusterSummary | null>(null)
  const [selectedCluster, setSelectedCluster] = useState(navState?.clusterId !== undefined ? String(navState.clusterId) : '')
  const [parcelIdsText, setParcelIdsText] = useState(navState?.parcelIds?.join(', ') ?? '')
  const [depotLat, setDepotLat] = useState(String(DEFAULT_DEPOT.latitude))
  const [depotLon, setDepotLon] = useState(String(DEFAULT_DEPOT.longitude))

  const [running, setRunning] = useState(false)
  const [runNotice, setRunNotice] = useState<Notice>(null)
  const [result, setResult] = useState<OptimizationResult | null>(null)

  const [vehicles, setVehicles] = useState<VirtualVehicle[]>([])
  const [vehiclesLoading, setVehiclesLoading] = useState(true)
  const [vehiclesNotice, setVehiclesNotice] = useState<Notice>(null)

  const [insertVehicleId, setInsertVehicleId] = useState('')
  const [insertDraft, setInsertDraft] = useState<ParcelDraft>(() => emptyParcelDraft())
  const [inserting, setInserting] = useState(false)
  const [insertNotice, setInsertNotice] = useState<Notice>(null)

  const refreshClusters = async () => {
    try {
      setClusterSummary(await parcelService.getClusterSummary())
    } catch {
      // Non-fatal: the cluster dropdown just stays empty until the request succeeds.
    }
  }

  const refreshVehicles = async () => {
    setVehiclesLoading(true)
    try {
      setVehicles(await optimizationService.listVirtualVehicles())
    } catch (err) {
      setVehiclesNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to load virtual vehicles.' })
    } finally {
      setVehiclesLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshClusters()
      void refreshVehicles()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  const clusterChoices = useMemo(() => {
    if (!clusterSummary) return []
    return Object.entries(clusterSummary)
      .map(([key, count]) => ({ id: parseClusterKey(key), count }))
      .filter((row): row is { id: number; count: number } => row.id !== null && row.id >= 0)
      .sort((a, b) => a.id - b.id)
  }, [clusterSummary])

  const handleRun = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setRunNotice(null)
    setResult(null)

    const lat = Number(depotLat)
    const lon = Number(depotLon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setRunNotice({ tone: 'error', text: 'Depot latitude/longitude must be numbers.' })
      return
    }

    const payload: OptimizationRunRequest = { depot_latitude: lat, depot_longitude: lon }
    if (mode === 'cluster') {
      if (selectedCluster === '') {
        setRunNotice({ tone: 'error', text: 'Choose a cluster to optimize.' })
        return
      }
      payload.cluster_id = Number(selectedCluster)
    } else {
      const ids = parseIdList(parcelIdsText)
      if (ids.length === 0) {
        setRunNotice({ tone: 'error', text: 'Enter at least one parcel ID.' })
        return
      }
      payload.parcel_ids = ids
    }

    setRunning(true)
    try {
      const response = await optimizationService.run(payload)
      setResult(response)
      setRunNotice({
        tone: 'success',
        text: `Optimization created ${response.virtual_vehicle_ids.length} virtual vehicle${response.virtual_vehicle_ids.length === 1 ? '' : 's'}.`,
      })
      await refreshVehicles()
    } catch (err) {
      setRunNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Optimization run failed.' })
    } finally {
      setRunning(false)
    }
  }

  const handleInsert = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setInsertNotice(null)
    if (!insertVehicleId) {
      setInsertNotice({ tone: 'error', text: 'Choose a virtual vehicle first.' })
      return
    }
    try {
      const payload = parcelDraftToInput(insertDraft)
      setInserting(true)
      const response = await optimizationService.insertParcel(insertVehicleId, payload)
      setInsertNotice({
        tone: response.inserted ? 'success' : 'error',
        text: `${response.reason} — ${formatNumber(response.remaining_weight_kg)} kg / ${response.remaining_volume_m3.toFixed(2)} m³ remaining.`,
      })
      if (response.inserted) {
        setInsertDraft(emptyParcelDraft())
        await refreshVehicles()
      }
    } catch (err) {
      setInsertNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Insertion failed.' })
    } finally {
      setInserting(false)
    }
  }

  return (
    <div>
      <PageHeader
        description="Multi-objective NSGA-II search for the best virtual vehicle type and load per cluster or parcel set."
        title="Load Optimization"
      />

      <div className="grid gap-5 xl:grid-cols-[1.6fr_0.9fr]">
        <Card title="Run Optimization">
          <div className="mb-4 inline-flex rounded-xl border border-fleet-line bg-slate-50 p-1">
            <button
              className={clsx('rounded-lg px-4 py-2 text-sm font-bold transition', mode === 'cluster' ? 'bg-white text-fleet-blue shadow-sm' : 'text-fleet-muted')}
              onClick={() => setMode('cluster')}
              type="button"
            >
              By Cluster
            </button>
            <button
              className={clsx('rounded-lg px-4 py-2 text-sm font-bold transition', mode === 'parcels' ? 'bg-white text-fleet-blue shadow-sm' : 'text-fleet-muted')}
              onClick={() => setMode('parcels')}
              type="button"
            >
              By Parcel IDs
            </button>
          </div>

          {runNotice && (
            <div className="mb-4">
              <InlineAlert tone={runNotice.tone}>{runNotice.text}</InlineAlert>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleRun}>
            {mode === 'cluster' ? (
              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-fleet-muted">Cluster</span>
                <select
                  className="focus-ring min-h-11 w-full rounded-xl border border-fleet-line bg-white px-3 text-sm font-semibold text-fleet-ink shadow-sm outline-none focus:ring-4 focus:ring-blue-100"
                  onChange={(event) => setSelectedCluster(event.target.value)}
                  value={selectedCluster}
                >
                  <option value="">Select a cluster…</option>
                  {clusterChoices.map((c) => (
                    <option key={c.id} value={String(c.id)}>
                      Cluster {c.id} · {c.count} parcels
                    </option>
                  ))}
                </select>
                {clusterChoices.length === 0 && (
                  <p className="mt-1.5 text-xs font-medium text-fleet-muted">
                    No clusters yet — train HDBSCAN on the Parcel Consolidation page first.
                  </p>
                )}
              </label>
            ) : (
              <label className="block">
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-fleet-muted">Parcel IDs</span>
                <textarea
                  className="focus-ring min-h-[88px] w-full rounded-xl border border-fleet-line bg-white px-3 py-2 text-sm font-semibold text-fleet-ink shadow-sm outline-none focus:ring-4 focus:ring-blue-100"
                  onChange={(event) => setParcelIdsText(event.target.value)}
                  placeholder="P001, P002, P003"
                  value={parcelIdsText}
                />
                <p className="mt-1.5 text-xs font-medium text-fleet-muted">Comma, space, or newline separated parcel IDs.</p>
              </label>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <LabeledInput label="Depot Latitude" onChange={setDepotLat} step="0.0001" type="number" value={depotLat} />
              <LabeledInput label="Depot Longitude" onChange={setDepotLon} step="0.0001" type="number" value={depotLon} />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-fleet-line/80 pt-4">
              <span className="text-xs font-semibold text-fleet-muted">
                Defaults to {DEFAULT_DEPOT.label} ({DEFAULT_DEPOT.latitude}, {DEFAULT_DEPOT.longitude}).
              </span>
              <PrimaryButton loading={running} type="submit">
                <Sparkles className="h-4 w-4" /> Run NSGA-II Optimization
              </PrimaryButton>
            </div>
          </form>
        </Card>

        <Card title="Vehicle Type Reference">
          <p className="mb-4 text-sm font-medium text-fleet-muted">Capacity ceiling per virtual vehicle type considered by NSGA-II.</p>
          <div className="space-y-3">
            {VEHICLE_CATALOG.map((entry) => {
              const Icon = VEHICLE_ICON[entry.type]
              return (
                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3" key={entry.type}>
                  <span className="flex items-center gap-2 font-extrabold text-fleet-ink">
                    <span className={clsx('grid h-8 w-8 place-items-center rounded-lg', vehicleToneClass(entry.type))}>
                      <Icon className="h-4 w-4" />
                    </span>
                    {entry.label}
                  </span>
                  <span className="text-right text-xs font-bold text-fleet-muted">
                    {entry.capacity_kg} kg
                    <br />
                    {entry.capacity_m3} m³
                  </span>
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      {result && (
        <div className="mt-5 space-y-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={VEHICLE_ICON[result.selected_vehicle.vehicle_type]}
              label="Selected Vehicle"
              tone="blue"
              value={result.selected_vehicle.vehicle_type.replace('_', ' ')}
            />
            <MetricCard icon={Gauge} label="Weight Utilization" tone="green" value={formatPercent(result.selected_vehicle.utilization_weight)} />
            <MetricCard icon={Route} label="Est. Distance" tone="amber" value={`${result.selected_vehicle.estimated_distance_km.toFixed(1)} km`} />
            <MetricCard
              icon={ListChecks}
              label="Time-Window Compliance"
              tone="blue"
              value={formatPercent(result.selected_vehicle.time_window_compliance)}
            />
          </div>

          <Card title="Selected Load">
            <div className="grid gap-5 sm:grid-cols-2">
              <CapacityBar capacity={result.selected_vehicle.capacity_kg} label="Weight" unit=" kg" used={result.selected_vehicle.load_weight_kg} />
              <CapacityBar capacity={result.selected_vehicle.capacity_m3} label="Volume" unit=" m³" used={result.selected_vehicle.load_volume_m3} />
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <StatusBadge tone="blue">{result.optimization_id}</StatusBadge>
              <Link className="rounded-lg bg-fleet-blue px-3 py-1.5 text-xs font-extrabold text-white" to={`/load-plans/${encodeURIComponent(result.optimization_id)}`}>View load plan</Link>
              {result.virtual_vehicle_ids.map((id) => <StatusBadge key={id} tone="green">{id}</StatusBadge>)}
              {result.cluster_id !== null && <StatusBadge tone="slate">{clusterLabel(result.cluster_id)}</StatusBadge>}
              <StatusBadge tone="slate">Fleet cost {formatNumber(result.selected_vehicle.fleet_cost)}</StatusBadge>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {result.parcel_ids.slice(0, 24).map((id) => (
                <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600" key={id}>
                  {id}
                </span>
              ))}
              {result.parcel_ids.length > 24 && (
                <span className="text-xs font-bold text-fleet-muted">+{result.parcel_ids.length - 24} more</span>
              )}
            </div>
          </Card>

          <Card title="Assigned Virtual Vehicle Loads">
            <DataTable headers={['Vehicle Type', 'Capacity', 'Load', 'Weight Util', 'Volume Util', 'Distance', 'Compliance', 'Cost']}>
              {result.vehicles.map((option, index) => (
                <ParetoRow key={option.virtual_vehicle_id} option={option} selected={index === 0} />
              ))}
            </DataTable>
          </Card>
        </div>
      )}

      <Card
        action={
          <SecondaryButton onClick={refreshVehicles}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </SecondaryButton>
        }
        className="mt-5"
        title="Virtual Vehicles Fleet"
      >
        {vehiclesNotice && (
          <div className="mb-4">
            <InlineAlert tone={vehiclesNotice.tone}>{vehiclesNotice.text}</InlineAlert>
          </div>
        )}
        {vehiclesLoading ? (
          <LoadingState message="Please wait while virtual vehicles are loading…" />
        ) : vehicles.length === 0 ? (
          <EmptyState
            description="Run an optimization above to generate the first virtual vehicle load."
            icon={PackageSearch}
            title="No virtual vehicles yet"
          />
        ) : (
          <DataTable headers={['Virtual Vehicle', 'Type', 'Weight Load', 'Volume Load', 'Cluster', 'Destination', 'Updated']}>
            {vehicles.map((vehicle) => {
              const Icon = VEHICLE_ICON[vehicle.vehicle_type]
              return (
                <tr className="transition hover:bg-blue-50/40" key={vehicle.virtual_vehicle_id}>
                  <td className="px-5 py-4 font-black text-fleet-ink">{vehicle.virtual_vehicle_id}</td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-2 font-bold">
                      <span className={clsx('grid h-7 w-7 place-items-center rounded-lg', vehicleToneClass(vehicle.vehicle_type))}>
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      {vehicle.vehicle_type.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="w-40 px-5 py-4">
                    <CapacityBar capacity={vehicle.capacity_kg} label="" unit=" kg" used={vehicle.used_weight_kg} />
                  </td>
                  <td className="w-40 px-5 py-4">
                    <CapacityBar capacity={vehicle.capacity_m3} label="" unit=" m³" used={vehicle.used_volume_m3} />
                  </td>
                  <td className="px-5 py-4">
                    <StatusBadge tone={vehicle.cluster_id !== null ? 'blue' : 'slate'}>{clusterLabel(vehicle.cluster_id)}</StatusBadge>
                  </td>
                  <td className="px-5 py-4 text-fleet-muted">
                    {vehicle.destination_latitude !== null && vehicle.destination_longitude !== null
                      ? `${vehicle.destination_latitude.toFixed(4)}, ${vehicle.destination_longitude.toFixed(4)}`
                      : '—'}
                  </td>
                  <td className="px-5 py-4 text-fleet-muted">{formatDateTime(vehicle.updated_at)}</td>
                </tr>
              )
            })}
          </DataTable>
        )}
      </Card>

      <Card className="mt-5" title="Insert Parcel into an Existing Virtual Vehicle">
        <p className="mb-4 text-sm font-medium text-fleet-muted">
          Dynamically appends a new parcel to a virtual vehicle if remaining weight/volume capacity allows.
        </p>
        {insertNotice && (
          <div className="mb-4">
            <InlineAlert tone={insertNotice.tone}>{insertNotice.text}</InlineAlert>
          </div>
        )}
        <form className="space-y-4" onSubmit={handleInsert}>
          <label className="block">
            <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-fleet-muted">Target Virtual Vehicle</span>
            <select
              className="focus-ring min-h-11 w-full rounded-xl border border-fleet-line bg-white px-3 text-sm font-semibold text-fleet-ink shadow-sm outline-none focus:ring-4 focus:ring-blue-100"
              onChange={(event) => setInsertVehicleId(event.target.value)}
              value={insertVehicleId}
            >
              <option value="">Select a virtual vehicle…</option>
              {vehicles.map((vehicle) => (
                <option key={vehicle.virtual_vehicle_id} value={vehicle.virtual_vehicle_id}>
                  {vehicle.virtual_vehicle_id} · {vehicle.vehicle_type} · {(vehicle.capacity_kg - vehicle.used_weight_kg).toFixed(1)} kg free
                </option>
              ))}
            </select>
          </label>
          <ParcelFieldsFieldset onChange={setInsertDraft} value={insertDraft} />
          <div className="flex items-center justify-end border-t border-fleet-line/80 pt-4">
            <PrimaryButton loading={inserting} type="submit">
              <MapPin className="h-4 w-4" /> Insert Parcel
            </PrimaryButton>
          </div>
        </form>
      </Card>
    </div>
  )
}

function ParetoRow({ option, selected }: { option: VehicleOption; selected: boolean }) {
  const Icon = VEHICLE_ICON[option.vehicle_type]
  return (
    <tr className={clsx('transition', selected ? 'bg-blue-50/60' : 'hover:bg-blue-50/30')}>
      <td className="px-5 py-4">
        <span className="flex items-center gap-2 font-black text-fleet-ink">
          <span className={clsx('grid h-8 w-8 place-items-center rounded-lg', vehicleToneClass(option.vehicle_type))}>
            <Icon className="h-4 w-4" />
          </span>
          {option.vehicle_type.replace('_', ' ')}
          {selected && <StatusBadge tone="green">Selected</StatusBadge>}
        </span>
      </td>
      <td className="px-5 py-4 text-fleet-muted">
        {option.capacity_kg} kg / {option.capacity_m3} m³
      </td>
      <td className="px-5 py-4 font-semibold">
        {option.load_weight_kg.toFixed(1)} kg / {option.load_volume_m3.toFixed(2)} m³
      </td>
      <td className="px-5 py-4 font-semibold">{formatPercent(option.utilization_weight)}</td>
      <td className="px-5 py-4 font-semibold">{formatPercent(option.utilization_volume)}</td>
      <td className="px-5 py-4 font-semibold">{option.estimated_distance_km.toFixed(1)} km</td>
      <td className="px-5 py-4 font-semibold">{formatPercent(option.time_window_compliance)}</td>
      <td className="px-5 py-4 font-black">{formatNumber(option.fleet_cost)}</td>
    </tr>
  )
}
