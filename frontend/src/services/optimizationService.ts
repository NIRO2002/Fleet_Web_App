import { api } from './api'
import type { InsertionResult, LoadPlan, OptimizationResult, OptimizationRunRequest, ParcelInput, VirtualVehicle } from '../types'

export const optimizationService = {
  run: (payload: OptimizationRunRequest) => api.post<OptimizationResult>('/optimization/run', payload),
  getPlan: (planId: string) => api.get<LoadPlan>(`/optimization/plans/${encodeURIComponent(planId)}`),
  planCsvUrl: (planId: string) => `/api/v1/optimization/plans/${encodeURIComponent(planId)}/export.csv`,

  listVirtualVehicles: () => api.get<VirtualVehicle[]>('/virtual-vehicles'),

  insertParcel: (virtualVehicleId: string, parcel: ParcelInput) =>
    api.post<InsertionResult>(`/virtual-vehicles/${encodeURIComponent(virtualVehicleId)}/insert-parcel`, parcel),
}
