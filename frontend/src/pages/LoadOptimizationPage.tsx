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
  ProgressBar,
  SecondaryButton,
  StatusBadge,
} from '../components/UI'
import { DEFAULT_DEPOT } from '../data/mockData'
import { ParetoParallelCoordinates } from '../components/ParetoParallelCoordinates'
import { optimizationService } from '../services/optimizationService'
import { vehicleTypeService } from '../services/vehicleTypeService'
import type {
  ClusterSummary,
  OptimizationResult,
  OptimizationRunRequest,
  ParcelDraft,
  VehicleOption,
  VehicleType,
  VehicleTypeCatalog,
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
import { readSession, writeSession } from '../utils/sessionStore'

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null

interface NavState {
  parcelIds?: string[]
  clusterId?: number
  clusterIds?: number[]
  // HDBSCAN labels restart at 0 per (depot_id, delivery_date) planning
  // instance, so cluster_id alone is ambiguous -- the backend now requires
  // this scope alongside cluster_id (see backend/app/api/v1/optimization.py).
  // Forwarded from ParcelConsolidationPage's "Continue to Optimization".
  depotId?: string
  deliveryDate?: string
  /** From the training run that produced clusterIds: parcels left
   * genuinely unassignable after HDBSCAN + repair. Never auto-optimized. */
  unassignedCount?: number
}

interface BatchResult {
  clusterId: number
  status: 'success' | 'error'
  result?: OptimizationResult
  message?: string
}

const VEHICLE_ICON_MAP: Record<string, LucideIcon> = {
  BIKE: Bike,
  APE_CARGO: Car,
  TVS_KING: Car,
  MICRO_VAN: Truck,
  VAN_MED: Truck,
  TRUCK_2T: Container,
  TRUCK_4T: Container,
}

/** Falls back to a generic truck icon for any vehicle type added to the
 * catalog beyond the original 7 field-data codes. */
const vehicleIcon = (type: VehicleType): LucideIcon => VEHICLE_ICON_MAP[type] ?? Truck

export function LoadOptimizationPage() {
  const location = useLocation()
  const navState = (location.state as NavState | null) ?? null

  // navState (an explicit "Optimize" click from another page) always wins over
  // whatever was left in this page's own session from a previous visit.
  const [mode, setMode] = useState<'cluster' | 'parcels' | 'all'>(() => {
    if (navState?.clusterIds && navState.clusterIds.length > 0) return 'all'
    if (navState?.parcelIds && navState.parcelIds.length > 0) return 'parcels'
    return readSession('optimize.mode', 'cluster')
  })
  const [clusterSummary] = useState<ClusterSummary | null>(null)
  const [selectedCluster, setSelectedCluster] = useState(() =>
    navState?.clusterId !== undefined ? String(navState.clusterId) : readSession('optimize.selectedCluster', ''),
  )
  const [parcelIdsText, setParcelIdsText] = useState(() => navState?.parcelIds?.join(', ') ?? readSession('optimize.parcelIdsText', ''))
  const [depotLat, setDepotLat] = useState(() => readSession('optimize.depotLat', String(DEFAULT_DEPOT.latitude)))
  const [depotLon, setDepotLon] = useState(() => readSession('optimize.depotLon', String(DEFAULT_DEPOT.longitude)))

  const [running, setRunning] = useState(false)
  const [runProgress, setRunProgress] = useState(0)
  const [runNotice, setRunNotice] = useState<Notice>(null)
  const [result, setResult] = useState<OptimizationResult | null>(() => readSession('optimize.result', null))

  useEffect(() => {
    writeSession('optimize.mode', mode)
  }, [mode])
  useEffect(() => {
    writeSession('optimize.selectedCluster', selectedCluster)
  }, [selectedCluster])
  useEffect(() => {
    writeSession('optimize.parcelIdsText', parcelIdsText)
  }, [parcelIdsText])
  useEffect(() => {
    writeSession('optimize.depotLat', depotLat)
  }, [depotLat])
  useEffect(() => {
    writeSession('optimize.depotLon', depotLon)
  }, [depotLon])
  useEffect(() => {
    writeSession('optimize.result', result)
  }, [result])

  useEffect(() => {
    if (!running) return
    setRunProgress(8)
    const timer = window.setInterval(() => {
      // Eases toward 90% while the request is in flight; real completion snaps to 100.
      setRunProgress((prev) => (prev >= 90 ? 90 : prev + (90 - prev) * 0.12))
    }, 250)
    return () => window.clearInterval(timer)
  }, [running])

  const [batchRunning, setBatchRunning] = useState(false)
  const [batchIndex, setBatchIndex] = useState(-1)
  const [batchClusterProgress, setBatchClusterProgress] = useState(0)
  const [batchResults, setBatchResults] = useState<BatchResult[]>(() => readSession('optimize.batchResults', []))

  useEffect(() => {
    writeSession('optimize.batchResults', batchResults)
  }, [batchResults])

  const [vehicles, setVehicles] = useState<VirtualVehicle[]>([])
  const [vehiclesLoading, setVehiclesLoading] = useState(true)
  const [vehiclesNotice, setVehiclesNotice] = useState<Notice>(null)

  const [vehicleTypes, setVehicleTypes] = useState<VehicleTypeCatalog[]>([])

  const [insertVehicleId, setInsertVehicleId] = useState('')
  const [insertDraft, setInsertDraft] = useState<ParcelDraft>(() => emptyParcelDraft())
  const [inserting, setInserting] = useState(false)
  const [insertNotice, setInsertNotice] = useState<Notice>(null)

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

  const refreshVehicleTypes = async () => {
    try {
      setVehicleTypes(await vehicleTypeService.list())
    } catch {
      // Non-fatal: the reference card just stays empty until the request succeeds.
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshVehicles()
      void refreshVehicleTypes()
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

  const batchClusterIds = useMemo(() => {
    if (navState?.clusterIds && navState.clusterIds.length > 0) return navState.clusterIds
    return clusterChoices.map((c) => c.id)
  }, [navState, clusterChoices])

  const handleRun = async () => {
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
      if (!navState?.depotId || !navState?.deliveryDate) {
        setRunNotice({ tone: 'error', text: 'Missing depot/delivery date scope for this cluster - return to Parcel Consolidation and continue from there.' })
        return
      }
      payload.cluster_id = Number(selectedCluster)
      payload.depot_id = navState.depotId
      payload.delivery_date = navState.deliveryDate
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
      setRunProgress(100)
      setResult(response)
      setRunNotice({
        tone: 'success',
        text: `Optimization created ${response.virtual_vehicle_ids.length} virtual vehicle${response.virtual_vehicle_ids.length === 1 ? '' : 's'}.`,
      })
      await refreshVehicles()
    } catch (err) {
      setRunProgress(0)
      setRunNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Optimization run failed.' })
    } finally {
      setRunning(false)
    }
  }

  const runBatch = async () => {
    setRunNotice(null)
    setResult(null)

    const lat = Number(depotLat)
    const lon = Number(depotLon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setRunNotice({ tone: 'error', text: 'Depot latitude/longitude must be numbers.' })
      return
    }
    if (batchClusterIds.length === 0) {
      setRunNotice({ tone: 'error', text: 'No clusters available to optimize.' })
      return
    }
    if (!navState?.depotId || !navState?.deliveryDate) {
      setRunNotice({ tone: 'error', text: 'Missing depot/delivery date scope for these clusters - return to Parcel Consolidation and continue from there.' })
      return
    }
    const { depotId, deliveryDate } = navState

    setBatchResults([])
    setBatchRunning(true)
    for (let i = 0; i < batchClusterIds.length; i += 1) {
      const clusterId = batchClusterIds[i]
      setBatchIndex(i)
      setBatchClusterProgress(8)
      const timer = window.setInterval(() => {
        setBatchClusterProgress((prev) => (prev >= 90 ? 90 : prev + (90 - prev) * 0.12))
      }, 200)
      try {
        const response = await optimizationService.run({
          cluster_id: clusterId,
          depot_id: depotId,
          delivery_date: deliveryDate,
          depot_latitude: lat,
          depot_longitude: lon,
        })
        setBatchClusterProgress(100)
        setBatchResults((prev) => [...prev, { clusterId, status: 'success', result: response }])
      } catch (err) {
        setBatchClusterProgress(100)
        setBatchResults((prev) => [
          ...prev,
          { clusterId, status: 'error', message: err instanceof Error ? err.message : 'Optimization failed.' },
        ])
      } finally {
        window.clearInterval(timer)
      }
    }
    setBatchRunning(false)
    setBatchIndex(-1)
    await refreshVehicles()
    setRunNotice({
      tone: 'success',
      text: `Optimized ${batchClusterIds.length} cluster${batchClusterIds.length === 1 ? '' : 's'}.`,
    })
  }

  const handleFormSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (mode === 'all') {
      await runBatch()
    } else {
      await handleRun()
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
        text: `${response.reason} - ${formatNumber(response.remaining_weight_kg)} kg / ${response.remaining_volume_m3.toFixed(2)} m³ remaining.`,
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
            <button
              className={clsx('rounded-lg px-4 py-2 text-sm font-bold transition', mode === 'all' ? 'bg-white text-fleet-blue shadow-sm' : 'text-fleet-muted')}
              onClick={() => setMode('all')}
              type="button"
            >
              All Clusters
            </button>
          </div>

          {runNotice && (
            <div className="mb-4">
              <InlineAlert tone={runNotice.tone}>{runNotice.text}</InlineAlert>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleFormSubmit}>
            {mode === 'all' ? (
              <div>
                <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-fleet-muted">
                  Clusters to optimize ({batchClusterIds.length})
                </span>
                {batchClusterIds.length === 0 ? (
                  <p className="text-xs font-medium text-fleet-muted">
                    No clusters yet - train HDBSCAN on the Parcel Consolidation page first.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {batchClusterIds.map((id, index) => (
                      <StatusBadge
                        key={id}
                        tone={batchRunning && index === batchIndex ? 'blue' : batchRunning && index < batchIndex ? 'green' : 'slate'}
                      >
                        {clusterLabel(id)}
                      </StatusBadge>
                    ))}
                  </div>
                )}
              </div>
            ) : mode === 'cluster' ? (
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
                    No clusters yet - train HDBSCAN on the Parcel Consolidation page first.
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

            {running && mode !== 'all' && (
              <ProgressBar detail="Running NSGA-II…" label="Optimizing" percent={runProgress} />
            )}

            {batchRunning && batchIndex >= 0 && (
              <ProgressBar
                detail={`Cluster ${batchIndex + 1} of ${batchClusterIds.length} · ${Math.round(batchClusterProgress)}%`}
                label={clusterLabel(batchClusterIds[batchIndex])}
                percent={batchClusterProgress}
              />
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-fleet-line/80 pt-4">
              <span className="text-xs font-semibold text-fleet-muted">
                Defaults to {DEFAULT_DEPOT.label} ({DEFAULT_DEPOT.latitude}, {DEFAULT_DEPOT.longitude}).
              </span>
              {mode === 'all' ? (
                <PrimaryButton loading={batchRunning} type="submit">
                  <Sparkles className="h-4 w-4" /> Optimize All Clusters
                </PrimaryButton>
              ) : (
                <PrimaryButton loading={running} type="submit">
                  <Sparkles className="h-4 w-4" /> Run NSGA-II Optimization
                </PrimaryButton>
              )}
            </div>
          </form>
        </Card>

        <Card title="Vehicle Type Reference">
          <p className="mb-4 text-sm font-medium text-fleet-muted">Capacity ceiling per virtual vehicle type considered by NSGA-II - live from the Vehicle Types catalog.</p>
          <div className="space-y-3">
            {vehicleTypes.length === 0 ? (
              <p className="text-xs font-medium text-fleet-muted">
                No vehicle types yet - add one on the Vehicle Types page.
              </p>
            ) : (
              vehicleTypes.map((entry) => {
                const Icon = vehicleIcon(entry.code)
                return (
                  <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3" key={entry.code}>
                    <span className="flex items-center gap-2 font-extrabold text-fleet-ink">
                      <span className={clsx('grid h-8 w-8 place-items-center rounded-lg', vehicleToneClass(entry.code))}>
                        <Icon className="h-4 w-4" />
                      </span>
                      {entry.display_name}
                    </span>
                    <span className="text-right text-xs font-bold text-fleet-muted">
                      {entry.capacity_kg} kg
                      <br />
                      {entry.capacity_m3} m³
                    </span>
                  </div>
                )
              })
            )}
          </div>
        </Card>
      </div>

      {result && (
        <div className="mt-5 space-y-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={vehicleIcon(result.selected_vehicle.vehicle_type)}
              label="Selected Vehicle"
              tone="blue"
              value={result.selected_vehicle.vehicle_type.replace('_', ' ')}
            />
            <MetricCard icon={Gauge} label="Weight Utilization" tone="green" value={`${formatPercent(result.selected_vehicle.utilization_weight)} · LKR ${formatNumber(result.selected_vehicle.cost_per_parcel)} / parcel`} />
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
          <Card title={`Pareto Front (${result.pareto_solutions.length} non-dominated solutions)`}>
            <ParetoParallelCoordinates solutions={result.pareto_solutions} />
          </Card>
        </div>
      )}

      {batchResults.length > 0 && (
        <Card className="mt-5" title={`Batch Results (${batchResults.length}/${batchClusterIds.length})`}>
          {!!navState?.unassignedCount && (
            <div className="mb-4">
              <InlineAlert tone="info">
                {navState.unassignedCount} parcel{navState.unassignedCount === 1 ? '' : 's'} from this planning instance could not be assigned to any cluster (HDBSCAN + capacity-aware repair) and {navState.unassignedCount === 1 ? "isn't" : "aren't"} included in this batch - see the Parcel Consolidation page.
              </InlineAlert>
            </div>
          )}
          <DataTable headers={['Cluster', 'Status', 'Vehicle Type', 'Weight Util', 'Distance', 'Cost', '']}>
            {batchResults.map((row) => (
              <tr className="transition hover:bg-blue-50/40" key={row.clusterId}>
                <td className="px-5 py-4 font-black text-fleet-ink">{clusterLabel(row.clusterId)}</td>
                <td className="px-5 py-4">
                  <StatusBadge tone={row.status === 'success' ? 'green' : 'red'}>{row.status === 'success' ? 'Optimized' : 'Failed'}</StatusBadge>
                </td>
                {row.status === 'success' && row.result ? (
                  <>
                    <td className="px-5 py-4 font-semibold">{row.result.selected_vehicle.vehicle_type.replace('_', ' ')}</td>
                    <td className="px-5 py-4 font-semibold">{formatPercent(row.result.selected_vehicle.utilization_weight)}<br/><span className="text-xs text-fleet-muted">LKR {formatNumber(row.result.selected_vehicle.cost_per_parcel)} / parcel</span></td>
                    <td className="px-5 py-4 font-semibold">{row.result.selected_vehicle.estimated_distance_km.toFixed(1)} km</td>
                    <td className="px-5 py-4 font-black">{formatNumber(row.result.selected_vehicle.fleet_cost)}</td>
                    <td className="px-5 py-4">
                      <Link className="text-xs font-black text-fleet-blue" to={`/load-plans/${encodeURIComponent(row.result.optimization_id)}`}>
                        View load plan
                      </Link>
                    </td>
                  </>
                ) : (
                  <td className="px-5 py-4 text-fleet-muted" colSpan={5}>{row.message}</td>
                )}
              </tr>
            ))}
          </DataTable>
        </Card>
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
              const Icon = vehicleIcon(vehicle.vehicle_type_code)
              return (
                <tr className="transition hover:bg-blue-50/40" key={vehicle.virtual_vehicle_id}>
                  <td className="px-5 py-4 font-black text-fleet-ink">{vehicle.virtual_vehicle_id}</td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-2 font-bold">
                      <span className={clsx('grid h-7 w-7 place-items-center rounded-lg', vehicleToneClass(vehicle.vehicle_type_code))}>
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      {vehicle.vehicle_type_code.replace('_', ' ')}
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
                      : '-'}
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
                  {vehicle.virtual_vehicle_id} · {vehicle.vehicle_type_code} · {(vehicle.capacity_kg - vehicle.used_weight_kg).toFixed(1)} kg free
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
  const Icon = vehicleIcon(option.vehicle_type)
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
      <td className="px-5 py-4 font-semibold">{formatPercent(option.utilization_weight)}<br/><span className="text-xs text-fleet-muted">LKR {formatNumber(option.cost_per_parcel)} / parcel</span></td>
      <td className="px-5 py-4 font-semibold">{formatPercent(option.utilization_volume)}<br/><span className="text-xs text-fleet-muted">LKR {formatNumber(option.cost_per_parcel)} / parcel</span></td>
      <td className="px-5 py-4 font-semibold">{option.estimated_distance_km.toFixed(1)} km</td>
      <td className="px-5 py-4 font-semibold">{formatPercent(option.time_window_compliance)}</td>
      <td className="px-5 py-4 font-black">{formatNumber(option.fleet_cost)}</td>
    </tr>
  )
}
