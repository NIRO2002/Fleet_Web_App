import type { User, VehicleType } from '../types'

/**
 * Reference constants mirrored from the backend so the UI can render context
 * (capacity legend, default depot) without an extra round trip. Source of truth
 * remains the backend (app/services/optimization_service.py VEHICLES, app/core/config.py).
 */
export const VEHICLE_CATALOG: { type: VehicleType; label: string; capacity_kg: number; capacity_m3: number }[] = [
  { type: 'BIKE', label: 'Bike', capacity_kg: 25, capacity_m3: 0.08 },
  { type: 'THREE_WHEEL', label: 'Three-Wheeler', capacity_kg: 150, capacity_m3: 0.8 },
  { type: 'VAN', label: 'Van', capacity_kg: 1000, capacity_m3: 8 },
  { type: 'LORRY', label: 'Lorry', capacity_kg: 5000, capacity_m3: 25 },
]

export const DEFAULT_DEPOT = {
  label: 'Colombo Depot',
  latitude: 6.9271,
  longitude: 79.8612,
}

export const CSV_TEMPLATE_COLUMNS = [
  'parcel_id',
  'latitude',
  'longitude',
  'weight_kg',
  'volume_m3',
  'time_window_start',
  'time_window_end',
  'fragile',
]

export const demoUser: User = {
  id: 'usr-planner-01',
  name: 'Operations Planner',
  email: 'planner@fleetopt.ai',
  role: 'planner',
  organization: 'FleetOpt AI Research Lab',
}
