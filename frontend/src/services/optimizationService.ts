import { api } from './api'
import type { InsertionResult, LoadPlan, OptimizationResult, OptimizationRunRequest, ParcelInput, ReadyVehicle, VirtualVehicle } from '../types'

export const optimizationService = {
  run: (payload: OptimizationRunRequest) => api.post<OptimizationResult>('/optimization/run', payload),
  getPlan: (planId: string) => api.get<LoadPlan>(`/optimization/plans/${encodeURIComponent(planId)}`),
  /** Most recent plan for a (depot_id, delivery_date), or null if none exists yet. */
  findPlan: (depotId: string, deliveryDate: string) =>
    api.get<LoadPlan | null>(`/optimization/plans?depot_id=${encodeURIComponent(depotId)}&delivery_date=${encodeURIComponent(deliveryDate)}`),
  planCsvUrl: (planId: string) => `/api/v1/optimization/plans/${encodeURIComponent(planId)}/export.csv`,

  listVirtualVehicles: () => api.get<VirtualVehicle[]>('/virtual-vehicles'),

  insertParcel: (virtualVehicleId: string, parcel: ParcelInput) =>
    api.post<InsertionResult>(`/virtual-vehicles/${encodeURIComponent(virtualVehicleId)}/insert-parcel`, parcel),

  markReady: (virtualVehicleId: string) =>
    api.patch<VirtualVehicle>(`/virtual-vehicles/${encodeURIComponent(virtualVehicleId)}/status`, { status: 'READY' }),

  listReadyVehicles: (depotId?: string, deliveryDate?: string) => {
    const params = new URLSearchParams()
    if (depotId) params.set('depot_id', depotId)
    if (deliveryDate) params.set('delivery_date', deliveryDate)
    const qs = params.toString()
    return api.get<ReadyVehicle[]>(`/vehicles/ready${qs ? `?${qs}` : ''}`)
  },
}
