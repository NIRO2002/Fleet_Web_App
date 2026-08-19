import type { ParcelDraft, ParcelInput, VehicleCapabilityDraft, VehicleCapabilityInput, VehicleType } from '../types'

export const formatNumber = (value: number) => value.toLocaleString('en-US')

export const formatPercent = (value: number, digits = 0) => `${(value * 100).toFixed(digits)}%`

export const formatKg = (value: number) => `${value.toFixed(1)} kg`

export const formatM3 = (value: number) => `${value.toFixed(3)} m³`

export const formatDateTime = (value: string) =>
  new Date(value).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })

/** Stable color per cluster id, cycling through the fleet accent palette. Noise/unclustered are always slate. */
const CLUSTER_PALETTE = ['#1d4ed8', '#16a34a', '#f59e0b', '#0284c7', '#dc2626', '#7c3aed', '#0d9488', '#db2777']

export const clusterColor = (clusterId: number | null) => {
  if (clusterId === null) return '#cbd5e1'
  if (clusterId < 0) return '#94a3b8'
  return CLUSTER_PALETTE[clusterId % CLUSTER_PALETTE.length]
}

/** null = HDBSCAN hasn't run yet; -1 = HDBSCAN labeled it noise; >=0 = a real cluster. */
export const clusterLabel = (clusterId: number | null) => {
  if (clusterId === null) return 'Not clustered yet'
  if (clusterId < 0) return 'Unassigned (noise)'
  return `Cluster ${clusterId}`
}

export const clusterTone = (clusterId: number | null): 'blue' | 'slate' => (clusterId !== null && clusterId >= 0 ? 'blue' : 'slate')

/** GET /parcels/clustering returns keys via Python's str(cluster_id): "None" | "-1" | "0" | "1" ... */
export const parseClusterKey = (key: string): number | null => (key === 'None' ? null : Number(key))

const VEHICLE_TONE: Record<VehicleType, string> = {
  BIKE: 'bg-slate-100 text-slate-700',
  APE_CARGO: 'bg-cyan-50 text-cyan-700',
  TVS_KING: 'bg-cyan-50 text-cyan-700',
  MICRO_VAN: 'bg-blue-50 text-blue-700',
  VAN_MED: 'bg-blue-50 text-blue-700',
  TRUCK_2T: 'bg-indigo-50 text-indigo-700',
  TRUCK_4T: 'bg-indigo-50 text-indigo-700',
}

export const vehicleToneClass = (type: VehicleType) => VEHICLE_TONE[type]

export const utilizationBarTone = (fraction: number) =>
  fraction >= 0.9 ? 'bg-red-500' : fraction >= 0.7 ? 'bg-amber-500' : 'bg-emerald-500'

export const emptyParcelDraft = (parcelId = ''): ParcelDraft => ({
  parcel_id: parcelId,
  latitude: '',
  longitude: '',
  weight_kg: '',
  volume_m3: '',
  time_window_start: '',
  time_window_end: '',
  fragile: false,
})

export const nextParcelId = (existing: string[]) => {
  let n = existing.length + 1
  const used = new Set(existing)
  while (used.has(`P${String(n).padStart(3, '0')}`)) n += 1
  return `P${String(n).padStart(3, '0')}`
}

export class ParcelDraftError extends Error {}

/** Parses + validates a ParcelDraft into the numeric ParcelInput the API expects. */
export const parcelDraftToInput = (draft: ParcelDraft): ParcelInput => {
  if (!draft.parcel_id.trim()) throw new ParcelDraftError('Parcel ID is required.')

  const latitude = Number(draft.latitude)
  const longitude = Number(draft.longitude)
  const weight_kg = Number(draft.weight_kg)
  const volume_m3 = Number(draft.volume_m3)

  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
    throw new ParcelDraftError('Latitude must be a number between -90 and 90.')
  }
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    throw new ParcelDraftError('Longitude must be a number between -180 and 180.')
  }
  if (!Number.isFinite(weight_kg) || weight_kg <= 0) {
    throw new ParcelDraftError('Weight must be a positive number.')
  }
  if (!Number.isFinite(volume_m3) || volume_m3 <= 0) {
    throw new ParcelDraftError('Volume must be a positive number.')
  }
  if (!/^\d{2}:\d{2}$/.test(draft.time_window_start) || !/^\d{2}:\d{2}$/.test(draft.time_window_end)) {
    throw new ParcelDraftError('Both time window fields are required (HH:MM).')
  }

  return {
    parcel_id: draft.parcel_id.trim(),
    latitude,
    longitude,
    weight_kg,
    volume_m3,
    time_window_start: draft.time_window_start,
    time_window_end: draft.time_window_end,
    fragile: draft.fragile,
  }
}

/** Normalizes lat/lon pairs into 0-100 (%) plot coordinates for the scatter panel. */
export const normalizePositions = (points: { latitude: number; longitude: number }[]) => {
  if (points.length === 0) return []
  const lats = points.map((p) => p.latitude)
  const lons = points.map((p) => p.longitude)
  const latMin = Math.min(...lats)
  const latMax = Math.max(...lats)
  const lonMin = Math.min(...lons)
  const lonMax = Math.max(...lons)
  const latSpan = latMax - latMin || 1
  const lonSpan = lonMax - lonMin || 1

  return points.map((p) => ({
    left: 8 + ((p.longitude - lonMin) / lonSpan) * 84,
    top: 8 + (1 - (p.latitude - latMin) / latSpan) * 84,
  }))
}

export const emptyVehicleCapabilityDraft = (): VehicleCapabilityDraft => ({
  name: '',
  category: '',
  brand: '',
  model: '',
  max_weight_kg: '',
  max_length_cm: '',
  max_width_cm: '',
  max_height_cm: '',
  status: 'ACTIVE',
})

export class VehicleCapabilityDraftError extends Error {}

/** Parses + validates a VehicleCapabilityDraft into the numeric input the API expects. */
export const vehicleCapabilityDraftToInput = (draft: VehicleCapabilityDraft): VehicleCapabilityInput => {
  if (!draft.name.trim()) throw new VehicleCapabilityDraftError('Vehicle name is required.')
  if (!draft.category.trim()) throw new VehicleCapabilityDraftError('Category is required.')

  const max_weight_kg = Number(draft.max_weight_kg)
  const max_length_cm = Number(draft.max_length_cm)
  const max_width_cm = Number(draft.max_width_cm)
  const max_height_cm = Number(draft.max_height_cm)

  if (!Number.isFinite(max_weight_kg) || max_weight_kg <= 0) {
    throw new VehicleCapabilityDraftError('Maximum weight must be a positive number.')
  }
  if (!Number.isFinite(max_length_cm) || max_length_cm <= 0) {
    throw new VehicleCapabilityDraftError('Length must be a positive number.')
  }
  if (!Number.isFinite(max_width_cm) || max_width_cm <= 0) {
    throw new VehicleCapabilityDraftError('Width must be a positive number.')
  }
  if (!Number.isFinite(max_height_cm) || max_height_cm <= 0) {
    throw new VehicleCapabilityDraftError('Height must be a positive number.')
  }

  return {
    name: draft.name.trim(),
    category: draft.category.trim(),
    brand: draft.brand.trim() || null,
    model: draft.model.trim() || null,
    max_weight_kg,
    max_length_cm,
    max_width_cm,
    max_height_cm,
    status: draft.status,
  }
}

export const vehicleCapabilityToDraft = (capability: {
  name: string
  category: string
  brand: string | null
  model: string | null
  max_weight_kg: number
  max_length_cm: number
  max_width_cm: number
  max_height_cm: number
  status: 'ACTIVE' | 'INACTIVE'
}): VehicleCapabilityDraft => ({
  name: capability.name,
  category: capability.category,
  brand: capability.brand ?? '',
  model: capability.model ?? '',
  max_weight_kg: String(capability.max_weight_kg),
  max_length_cm: String(capability.max_length_cm),
  max_width_cm: String(capability.max_width_cm),
  max_height_cm: String(capability.max_height_cm),
  status: capability.status,
})

export const parseIdList = (raw: string): string[] =>
  Array.from(
    new Set(
      raw
        .split(/[\s,]+/)
        .map((id) => id.trim())
        .filter(Boolean),
    ),
  )
