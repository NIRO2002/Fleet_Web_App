import type { User, VehicleType } from '../types'

/**
 * Reference constants mirrored from the backend so the UI can render context
 * (capacity legend, default depot) without an extra round trip. Source of truth
 * remains the backend (app/services/optimization_service.py VEHICLES, app/core/config.py).
 */
export const VEHICLE_CATALOG: { type: VehicleType; label: string; capacity_kg: number; capacity_m3: number }[] = [
  { type: 'BIKE', label: 'Bike', capacity_kg: 25, capacity_m3: 0.07 },
  { type: 'APE_CARGO', label: 'Ape Cargo', capacity_kg: 496, capacity_m3: 2.9 },
  { type: 'TVS_KING', label: 'TVS King', capacity_kg: 450, capacity_m3: 3.4 },
  { type: 'MICRO_VAN', label: 'Micro Van', capacity_kg: 350, capacity_m3: 2.98 },
  { type: 'VAN_MED', label: 'Medium Van', capacity_kg: 1100, capacity_m3: 6 },
  { type: 'TRUCK_2T', label: '2T Truck', capacity_kg: 2500, capacity_m3: 12.48 },
  { type: 'TRUCK_4T', label: '4T Truck', capacity_kg: 4500, capacity_m3: 24.02 },
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
