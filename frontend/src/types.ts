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
  dataset_id?: string | null
  depot_id?: string | null
  delivery_date?: string | null
  latitude: number
  longitude: number
  weight_kg: number
  volume_m3: number
  time_window_start: string // "HH:MM"
  time_window_end: string // "HH:MM"
  fragile: boolean
  length_cm?: number | null
  width_cm?: number | null
  height_cm?: number | null
  stackable: boolean
  max_stack_weight_kg: number
  loading_orientation_fixed: boolean
  hazardous: boolean
  hazmat_class?: string | null
  requires_refrigeration: boolean
  temp_min_celsius?: number | null
  temp_max_celsius?: number | null
  two_person_lift: boolean
  do_not_tilt: boolean
  priority_level: string
  service_type: string
}

export interface Parcel extends ParcelInput {
  cluster_id: number | null
  cluster_probability: number | null
  status: string
  dimensions_imputed: boolean
  is_noise: boolean
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
  dataset_id: string
  depot_id: string
  delivery_date: string
  length_cm: string
  width_cm: string
  height_cm: string
  stackable: boolean
  max_stack_weight_kg: string
  loading_orientation_fixed: boolean
  hazardous: boolean
  hazmat_class: string
  requires_refrigeration: boolean
  temp_min_celsius: string
  temp_max_celsius: string
  two_person_lift: boolean
  do_not_tilt: boolean
  priority_level: string
  service_type: string
}

export interface PaginatedParcels { items: Parcel[]; total: number; limit: number; offset: number }
export interface Depot { depot_id: string; depot_name: string; lat: number; lng: number }
export interface PlanSummary { plan_id: string; depot_id: string; delivery_date: string; created_at: string; vehicle_count: number; feasible: boolean }

export interface ClusterPrediction {
  // Always null: the persisted cluster_id is post-capacity-repair
  // (split/merge against vehicle_type_catalog), which a raw HDBSCAN
  // prediction cannot be reliably translated into. See backend
  // docs/DESIGN_DECISIONS.md's "predict_cluster cannot return a
  // post-repair cluster_id" entry.
  cluster_id: null
  cluster_probability: number
  status: 'UNASSIGNED'
  reason: string
}

/** Keyed by cluster_id as a string ("-1" = noise/unassigned). */
export type ClusterSummary = Record<string, number>

export interface ClusteringRepairSummary {
  applied: boolean
  n_split: number
  n_merged: number
  excluded_infeasible_count: number
}

export interface ClusteringTrainResult {
  status: string
  parcel_count: number
  /** HDBSCAN's raw cluster count, before capacity-aware repair's
   * split/merge. Will disagree with n_clusters_post_repair (and with the
   * `clusters` summary below, which reflects the post-repair, actually
   * persisted state) whenever repair changed anything. */
  n_clusters_pre_repair: number
  /** What's actually persisted after repair's split/merge (and any
   * infeasible cluster reassigned to -1/unassigned). */
  n_clusters_post_repair: number
  noise_count: number
  /** Final, post-repair count of parcels left genuinely unassignable
   * (cluster_id still -1) - smaller than noise_count, which is HDBSCAN's
   * raw pre-reassignment noise. See GET /parcels/clustering/unassigned. */
  unassigned_count: number
  /** Positive persisted clusters containing exactly one parcel. */
  n_singleton_clusters: number
  /** Positive persisted clusters containing fewer than six parcels. This is
   * reporting only; it does not currently change repair feasibility. */
  n_clusters_below_viability: number
  runtime_seconds: number
  repair: ClusteringRepairSummary
  clusters: ClusterSummary
}

export interface CsvUploadResult {
  dataset_id: string
  inserted: number
  updated: number
  skipped: number
  failed: number
  processed: number
  total_rows: number
  duplicates_removed: number
  dimensions_imputed_count: number
  errors: Array<{ row: number; field: string; reason: string }>
  warnings: Array<{ row: number; field: string; reason: string }>
}

// --- Optimization (mirrors backend app/schemas/optimization.py) ----------

/** The 7 field-data codes seeded into `vehicle_type_catalog` (see backend
 * app/db/seed_vehicle_types.py). Kept for icon/tone lookups and
 * autocomplete, but the catalog is admin-editable, so `VehicleType` itself
 * is NOT closed to these -- any string `vehicle_type_catalog` accepts is a
 * valid vehicle type at runtime. */
export type KnownVehicleType = 'BIKE' | 'APE_CARGO' | 'TVS_KING' | 'MICRO_VAN' | 'VAN_MED' | 'TRUCK_2T' | 'TRUCK_4T'
export type VehicleType = KnownVehicleType | (string & {})

export interface OptimizationRunRequest {
  cluster_id?: number
  parcel_ids?: string[]
  // Required by the backend whenever cluster_id is set: HDBSCAN labels
  // restart at 0 per (depot_id, delivery_date) planning instance, so a bare
  // cluster_id is ambiguous without this scope (see
  // backend/app/api/v1/optimization.py).
  depot_id?: string
  delivery_date?: string
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
  plan_id?: string
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

// --- Vehicle Type Catalog (mirrors backend app/schemas/vehicle_type.py) ---
// The single source of truth for vehicle specs: both the Vehicle Types CRUD
// page and NSGA-II read/write this same catalog, keyed by `code`.

export interface VehicleTypeCatalogInput {
  code: string
  display_name: string
  category: string | null
  model_name: string | null

  capacity_kg: number
  capacity_m3: number
  cargo_length_cm: number
  cargo_width_cm: number
  cargo_height_cm: number
  max_parcels: number
  max_stack_layers: number
  vehicle_max_stack_weight_kg: number

  fixed_cost: number
  cost_per_km: number
  avg_speed_kmh: number
  max_speed_kmh: number | null
  gross_vehicle_weight_kg: number | null

  available_from: string
  available_until: string

  is_refrigerated: boolean
  temp_min_celsius: number | null
  temp_max_celsius: number | null
  is_hazmat_certified: boolean
  has_tail_lift: boolean
  min_road_width_m: number | null

  cost_per_trip_reference: number | null
  source_reference: string | null
  depot_id: string | null
  source: string | null
  is_active: boolean
}

export interface VehicleTypeCatalog extends VehicleTypeCatalogInput {
  created_at: string
  updated_at: string
}

/** String-valued mirror of VehicleTypeCatalogInput used for controlled form fields. */
export interface VehicleTypeCatalogDraft {
  code: string
  display_name: string
  category: string
  model_name: string

  capacity_kg: string
  capacity_m3: string
  cargo_length_cm: string
  cargo_width_cm: string
  cargo_height_cm: string
  max_parcels: string
  max_stack_layers: string
  vehicle_max_stack_weight_kg: string

  fixed_cost: string
  cost_per_km: string
  avg_speed_kmh: string
  max_speed_kmh: string
  gross_vehicle_weight_kg: string

  available_from: string
  available_until: string

  is_refrigerated: boolean
  temp_min_celsius: string
  temp_max_celsius: string
  is_hazmat_certified: boolean
  has_tail_lift: boolean
  min_road_width_m: string

  cost_per_trip_reference: string
  source_reference: string
  depot_id: string
  source: string
  is_active: boolean
}
