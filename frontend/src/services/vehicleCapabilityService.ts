import { api } from './api'
import type { VehicleCapability, VehicleCapabilityInput } from '../types'

export const vehicleCapabilityService = {
  list: () => api.get<VehicleCapability[]>('/vehicle-capabilities'),
  get: (id: number) => api.get<VehicleCapability>(`/vehicle-capabilities/${id}`),
  create: (payload: VehicleCapabilityInput) => api.post<VehicleCapability>('/vehicle-capabilities', payload),
  update: (id: number, payload: VehicleCapabilityInput) => api.put<VehicleCapability>(`/vehicle-capabilities/${id}`, payload),
  remove: (id: number) => api.del<void>(`/vehicle-capabilities/${id}`),
}
