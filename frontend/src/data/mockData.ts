import type { User } from '../types'

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
  'depot_id',
  'delivery_date',
  'length_cm',
  'width_cm',
  'height_cm',
  'stackable',
  'max_stack_weight_kg',
  'loading_orientation_fixed',
  'hazardous',
  'hazmat_class',
  'requires_refrigeration',
  'temp_min_celsius',
  'temp_max_celsius',
  'two_person_lift',
  'do_not_tilt',
  'priority_level',
  'service_type',
]

export const demoUser: User = {
  id: 'usr-planner-01',
  name: 'Operations Planner',
  email: 'planner@fleetopt.ai',
  role: 'planner',
  organization: 'FleetOpt AI Research Lab',
}
