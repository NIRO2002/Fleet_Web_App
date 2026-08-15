import { api } from './api'
import type { InsertionResult, OptimizationResult, OptimizationRunRequest, ParcelInput, VirtualVehicle } from '../types'

export const optimizationService = {
  run: (payload: OptimizationRunRequest) => api.post<OptimizationResult>('/optimization/run', payload),

  listVirtualVehicles: () => api.get<VirtualVehicle[]>('/virtual-vehicles'),

  insertParcel: (virtualVehicleId: string, parcel: ParcelInput) =>
    api.post<InsertionResult>(`/virtual-vehicles/${encodeURIComponent(virtualVehicleId)}/insert-parcel`, parcel),
}
