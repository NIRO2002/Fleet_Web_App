export type UserRole = 'admin' | 'planner'

export interface User {
  id: string
  name: string
  email: string
  role: UserRole
  organization: string
}

// --- Parcels (mirrors backend app/schemas/parcel.py) ---------------------

export interface ParcelInput {
  parcel_id: string
  latitude: number
  longitude: number
  weight_kg: number
  volume_m3: number
  time_window_start: string // "HH:MM"
  time_window_end: string // "HH:MM"
  fragile: boolean
}

export interface Parcel extends ParcelInput {
  cluster_id: number | null
  cluster_probability: number | null
}

/** String-valued mirror of ParcelInput used for controlled form fields. */
export interface ParcelDraft {
  parcel_id: string
  latitude: string
  longitude: string
  weight_kg: string
  volume_m3: string
  time_window_start: string
  time_window_end: string
  fragile: boolean
}

export interface ClusterPrediction {
  cluster_id: number | null
  cluster_probability: number
  status: 'ASSIGNED' | 'UNASSIGNED'
}

/** Keyed by cluster_id as a string ("-1" = noise/unassigned). */
export type ClusterSummary = Record<string, number>

export interface ClusteringTrainResult {
  status: string
  parcel_count: number
  clusters: ClusterSummary
}

export interface CsvUploadResult {
  inserted: number
  skipped: number
}

// --- Optimization (mirrors backend app/schemas/optimization.py) ----------

export type VehicleType = 'BIKE' | 'APE_CARGO' | 'TVS_KING' | 'MICRO_VAN' | 'VAN_MED' | 'TRUCK_2T' | 'TRUCK_4T'

export interface OptimizationRunRequest {
  cluster_id?: number
  parcel_ids?: string[]
  depot_latitude?: number
  depot_longitude?: number
}

export interface VehicleOption {
  vehicle_type: VehicleType
  capacity_kg: number
  capacity_m3: number
  load_weight_kg: number
  load_volume_m3: number
  utilization_weight: number
  utilization_volume: number
  estimated_distance_km: number
  time_window_compliance: number
  fleet_cost: number
  virtual_vehicle_id: string
}

export interface OptimizationResult {
  optimization_id: string
  selected_vehicle: VehicleOption
  vehicles: VehicleOption[]
  parcel_ids: string[]
  cluster_id: number | null
  virtual_vehicle_id: string | null
  virtual_vehicle_ids: string[]
}

export interface LoadPlanParcel {
  parcel_id: string
  delivery_sequence: number
  load_sequence: number
  stack_layer: number
  load_position_x: number
  load_position_y: number
  load_position_z: number
  length_cm: number | null
  width_cm: number | null
  height_cm: number | null
  weight_kg: number
  volume_m3: number
  fragile: boolean
  stackable: boolean
  time_window_start: string
  time_window_end: string
}

export interface LoadPlanVehicle {
  virtual_vehicle_id: string
  vehicle_type: VehicleType
  status: 'PLANNED' | 'LOADING' | 'READY'
  ready_at: string | null
  capacity_kg: number
  capacity_m3: number
  used_weight_kg: number
  used_volume_m3: number
  utilization: number
  parcel_count: number
  cargo_length_cm: number
  cargo_width_cm: number
  cargo_height_cm: number
  estimated_distance_km: number
  time_window_compliance: number | null
  fleet_cost: number | null
  parcels: LoadPlanParcel[]
}

export interface LoadPlan {
  plan_id: string
  depot_id: string
  delivery_date: string
  status: string
  n_parcels: number
  n_vehicles: number
  mean_utilization: number
  total_distance_km: number
  mean_time_window_compliance: number
  total_fleet_cost: number
  vehicles: LoadPlanVehicle[]
}

export interface VirtualVehicle {
  virtual_vehicle_id: string
  vehicle_type_code: VehicleType
  status: 'PLANNED' | 'LOADING' | 'READY'
  ready_at: string | null
  capacity_kg: number
  capacity_m3: number
  used_weight_kg: number
  used_volume_m3: number
  parcel_count: number
  max_parcels: number | null
  utilization: number
  is_refrigerated: boolean
  is_hazmat_certified: boolean
  cluster_id: number | null
  destination_latitude: number | null
  destination_longitude: number | null
  updated_at: string
}

// --- Loaded Vehicles / fleet-optimizer handoff ("READY") -----------------

export interface ReadyVehicleStop {
  parcelId: string
  lat: number
  lng: number
  deliverySequence: number
  timeWindowStart: string
  timeWindowEnd: string
}

export interface ReadyVehicle {
  vehicleId: string
  vehicleType: VehicleType
  vehicleTypeName: string
  status: 'READY'
  loadPlanId: string
  depotId: string
  deliveryDate: string
  parcelCount: number
  utilization: number
  totalWeightKg: number
  totalVolumeM3: number
  readyAt: string | null
  stops: ReadyVehicleStop[]
}

export interface InsertionResult {
  virtual_vehicle_id: string
  inserted: boolean
  reason: string
  remaining_weight_kg: number
  remaining_volume_m3: number
}

// --- Vehicle Capabilities (mirrors backend app/schemas/vehicle_capability.py) ---
// A capability/type definition (e.g. "Bajaj Three Wheeler") — not a physical,
// registered vehicle. Registered Vehicles will reference these once that
// feature exists.

export type VehicleCapabilityStatus = 'ACTIVE' | 'INACTIVE'

export interface VehicleCapabilityInput {
  name: string
  category: string
  brand: string | null
  model: string | null
  max_weight_kg: number
  max_length_cm: number
  max_width_cm: number
  max_height_cm: number
  status: VehicleCapabilityStatus
}

export interface VehicleCapability extends VehicleCapabilityInput {
  id: number
  max_volume_m3: number
  created_at: string
  updated_at: string
}

/** String-valued mirror of VehicleCapabilityInput used for controlled form fields. */
export interface VehicleCapabilityDraft {
  name: string
  category: string
  brand: string
  model: string
  max_weight_kg: string
  max_length_cm: string
  max_width_cm: string
  max_height_cm: string
  status: VehicleCapabilityStatus
}
