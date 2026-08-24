import type { KnownVehicleType, ParcelDraft, ParcelInput, VehicleTypeCatalogDraft, VehicleTypeCatalogInput, VehicleType } from '../types'

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

const VEHICLE_TONE: Record<KnownVehicleType, string> = {
  BIKE: 'bg-slate-100 text-slate-700',
  APE_CARGO: 'bg-cyan-50 text-cyan-700',
  TVS_KING: 'bg-cyan-50 text-cyan-700',
  MICRO_VAN: 'bg-blue-50 text-blue-700',
  VAN_MED: 'bg-blue-50 text-blue-700',
  TRUCK_2T: 'bg-indigo-50 text-indigo-700',
  TRUCK_4T: 'bg-indigo-50 text-indigo-700',
}

const DEFAULT_VEHICLE_TONE = 'bg-slate-100 text-slate-700'

/** Falls back to a neutral tone for any vehicle type added to the catalog
 * beyond the original 7 field-data codes. */
export const vehicleToneClass = (type: VehicleType) => VEHICLE_TONE[type as KnownVehicleType] ?? DEFAULT_VEHICLE_TONE

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
  dataset_id: '', depot_id: '', delivery_date: '', length_cm: '', width_cm: '', height_cm: '',
  stackable: true, max_stack_weight_kg: '0', loading_orientation_fixed: false,
  hazardous: false, hazmat_class: '', requires_refrigeration: false,
  temp_min_celsius: '', temp_max_celsius: '', two_person_lift: false, do_not_tilt: false,
  priority_level: 'standard', service_type: 'door_to_door',
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
  if (draft.time_window_end <= draft.time_window_start) throw new ParcelDraftError('Time window end must be after its start.')
  const dimensions = [draft.length_cm, draft.width_cm, draft.height_cm]
  if (dimensions.some(Boolean) && !dimensions.every(Boolean)) throw new ParcelDraftError('Provide all three dimensions or leave all three blank.')
  const numberOrNull = (raw: string) => raw.trim() ? Number(raw) : null
  const length_cm = numberOrNull(draft.length_cm), width_cm = numberOrNull(draft.width_cm), height_cm = numberOrNull(draft.height_cm)
  if ([length_cm, width_cm, height_cm].some((v) => v !== null && (!Number.isFinite(v) || v <= 0))) throw new ParcelDraftError('Dimensions must be positive numbers.')
  const max_stack_weight_kg = Number(draft.max_stack_weight_kg || 0)
  if (!Number.isFinite(max_stack_weight_kg) || max_stack_weight_kg < 0) throw new ParcelDraftError('Max stack weight must be zero or greater.')
  const temp_min_celsius = draft.requires_refrigeration ? numberOrNull(draft.temp_min_celsius) : null
  const temp_max_celsius = draft.requires_refrigeration ? numberOrNull(draft.temp_max_celsius) : null
  if (temp_min_celsius !== null && temp_max_celsius !== null && temp_min_celsius > temp_max_celsius) throw new ParcelDraftError('Minimum temperature cannot exceed maximum temperature.')

  return {
    parcel_id: draft.parcel_id.trim(),
    latitude,
    longitude,
    weight_kg,
    volume_m3,
    time_window_start: draft.time_window_start,
    time_window_end: draft.time_window_end,
    fragile: draft.fragile,
    dataset_id: draft.dataset_id.trim() || null, depot_id: draft.depot_id, delivery_date: draft.delivery_date,
    length_cm, width_cm, height_cm, stackable: draft.stackable, max_stack_weight_kg,
    loading_orientation_fixed: draft.loading_orientation_fixed, hazardous: draft.hazardous,
    hazmat_class: draft.hazardous ? draft.hazmat_class.trim() || null : null,
    requires_refrigeration: draft.requires_refrigeration, temp_min_celsius, temp_max_celsius,
    two_person_lift: draft.two_person_lift, do_not_tilt: draft.do_not_tilt,
    priority_level: draft.priority_level, service_type: draft.service_type,
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

export const emptyVehicleTypeDraft = (): VehicleTypeCatalogDraft => ({
  code: '',
  display_name: '',
  category: '',
  model_name: '',
  capacity_kg: '',
  capacity_m3: '',
  cargo_length_cm: '',
  cargo_width_cm: '',
  cargo_height_cm: '',
  max_parcels: '',
  max_stack_layers: '1',
  vehicle_max_stack_weight_kg: '1000000',
  fixed_cost: '',
  cost_per_km: '',
  avg_speed_kmh: '',
  max_speed_kmh: '',
  gross_vehicle_weight_kg: '',
  available_from: '00:00',
  available_until: '23:59',
  is_refrigerated: false,
  temp_min_celsius: '',
  temp_max_celsius: '',
  is_hazmat_certified: false,
  has_tail_lift: false,
  min_road_width_m: '',
  cost_per_trip_reference: '',
  source_reference: '',
  depot_id: '',
  source: '',
  is_active: true,
})

export class VehicleTypeDraftError extends Error {}

const requirePositiveNumber = (raw: string, field: string): number => {
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) throw new VehicleTypeDraftError(`${field} must be a positive number.`)
  return value
}

const optionalNumber = (raw: string): number | null => {
  const trimmed = raw.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  if (!Number.isFinite(value)) throw new VehicleTypeDraftError('Expected a number.')
  return value
}

/** Parses + validates a VehicleTypeCatalogDraft into the numeric input the API expects. */
export const vehicleTypeDraftToInput = (draft: VehicleTypeCatalogDraft): VehicleTypeCatalogInput => {
  if (!draft.code.trim()) throw new VehicleTypeDraftError('Code is required.')
  if (!draft.display_name.trim()) throw new VehicleTypeDraftError('Display name is required.')
  if (!/^\d{2}:\d{2}$/.test(draft.available_from) || !/^\d{2}:\d{2}$/.test(draft.available_until)) {
    throw new VehicleTypeDraftError('Both operating-window fields are required (HH:MM).')
  }

  const max_parcels = Number(draft.max_parcels)
  const max_stack_layers = Number(draft.max_stack_layers)
  if (!Number.isInteger(max_parcels) || max_parcels <= 0) {
    throw new VehicleTypeDraftError('Max parcels must be a positive whole number.')
  }
  if (!Number.isInteger(max_stack_layers) || max_stack_layers < 1) {
    throw new VehicleTypeDraftError('Max stack layers must be a whole number of at least 1.')
  }

  return {
    code: draft.code.trim().toUpperCase(),
    display_name: draft.display_name.trim(),
    category: draft.category.trim() || null,
    model_name: draft.model_name.trim() || null,
    capacity_kg: requirePositiveNumber(draft.capacity_kg, 'Capacity (kg)'),
    capacity_m3: requirePositiveNumber(draft.capacity_m3, 'Capacity (m³)'),
    cargo_length_cm: requirePositiveNumber(draft.cargo_length_cm, 'Cargo length'),
    cargo_width_cm: requirePositiveNumber(draft.cargo_width_cm, 'Cargo width'),
    cargo_height_cm: requirePositiveNumber(draft.cargo_height_cm, 'Cargo height'),
    max_parcels,
    max_stack_layers,
    vehicle_max_stack_weight_kg: optionalNumber(draft.vehicle_max_stack_weight_kg) ?? 1_000_000,
    fixed_cost: optionalNumber(draft.fixed_cost) ?? 0,
    cost_per_km: optionalNumber(draft.cost_per_km) ?? 0,
    avg_speed_kmh: requirePositiveNumber(draft.avg_speed_kmh, 'Average speed'),
    max_speed_kmh: optionalNumber(draft.max_speed_kmh),
    gross_vehicle_weight_kg: optionalNumber(draft.gross_vehicle_weight_kg),
    available_from: draft.available_from,
    available_until: draft.available_until,
    is_refrigerated: draft.is_refrigerated,
    temp_min_celsius: optionalNumber(draft.temp_min_celsius),
    temp_max_celsius: optionalNumber(draft.temp_max_celsius),
    is_hazmat_certified: draft.is_hazmat_certified,
    has_tail_lift: draft.has_tail_lift,
    min_road_width_m: optionalNumber(draft.min_road_width_m),
    cost_per_trip_reference: optionalNumber(draft.cost_per_trip_reference),
    source_reference: draft.source_reference.trim() || null,
    depot_id: draft.depot_id.trim() || null,
    source: draft.source.trim() || null,
    is_active: draft.is_active,
  }
}

export const vehicleTypeToDraft = (vehicleType: VehicleTypeCatalogInput): VehicleTypeCatalogDraft => ({
  code: vehicleType.code,
  display_name: vehicleType.display_name,
  category: vehicleType.category ?? '',
  model_name: vehicleType.model_name ?? '',
  capacity_kg: String(vehicleType.capacity_kg),
  capacity_m3: String(vehicleType.capacity_m3),
  cargo_length_cm: String(vehicleType.cargo_length_cm),
  cargo_width_cm: String(vehicleType.cargo_width_cm),
  cargo_height_cm: String(vehicleType.cargo_height_cm),
  max_parcels: String(vehicleType.max_parcels),
  max_stack_layers: String(vehicleType.max_stack_layers),
  vehicle_max_stack_weight_kg: String(vehicleType.vehicle_max_stack_weight_kg),
  fixed_cost: String(vehicleType.fixed_cost),
  cost_per_km: String(vehicleType.cost_per_km),
  avg_speed_kmh: String(vehicleType.avg_speed_kmh),
  max_speed_kmh: vehicleType.max_speed_kmh === null ? '' : String(vehicleType.max_speed_kmh),
  gross_vehicle_weight_kg: vehicleType.gross_vehicle_weight_kg === null ? '' : String(vehicleType.gross_vehicle_weight_kg),
  available_from: vehicleType.available_from,
  available_until: vehicleType.available_until,
  is_refrigerated: vehicleType.is_refrigerated,
  temp_min_celsius: vehicleType.temp_min_celsius === null ? '' : String(vehicleType.temp_min_celsius),
  temp_max_celsius: vehicleType.temp_max_celsius === null ? '' : String(vehicleType.temp_max_celsius),
  is_hazmat_certified: vehicleType.is_hazmat_certified,
  has_tail_lift: vehicleType.has_tail_lift,
  min_road_width_m: vehicleType.min_road_width_m === null ? '' : String(vehicleType.min_road_width_m),
  cost_per_trip_reference: vehicleType.cost_per_trip_reference === null ? '' : String(vehicleType.cost_per_trip_reference),
  source_reference: vehicleType.source_reference ?? '',
  depot_id: vehicleType.depot_id ?? '',
  source: vehicleType.source ?? '',
  is_active: vehicleType.is_active,
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
