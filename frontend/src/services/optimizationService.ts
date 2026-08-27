import { api } from './api'
import type { InsertionResult, LoadPlan, OptimizationBatchResult, OptimizationJob, OptimizationResult, OptimizationRunRequest, ParcelInput, PlanSummary, ReadyVehicle, VirtualVehicle } from '../types'

export const optimizationService = {
  run: (payload: OptimizationRunRequest) => api.post<OptimizationResult>('/optimization/run', payload),
  createJob: (payload: OptimizationRunRequest) => api.post<OptimizationJob>('/optimization/jobs', payload),
  createBatch: (payload: { cluster_ids: number[]; depot_id: string; delivery_date: string; depot_latitude?: number; depot_longitude?: number }) =>
    api.post<OptimizationBatchResult>('/optimization/jobs/batch', payload),
  getJob: (jobId: string) => api.get<OptimizationJob>(`/optimization/jobs/${encodeURIComponent(jobId)}`),
  listJobs: (params?: { status?: string; depot_id?: string; delivery_date?: string; batch_id?: string }) => {
    const query = new URLSearchParams()
    Object.entries(params ?? {}).forEach(([key, value]) => { if (value) query.set(key, value) })
    return api.get<OptimizationJob[]>(`/optimization/jobs${query.size ? `?${query}` : ''}`)
  },
  getPlan: (planId: string) => api.get<LoadPlan>(`/optimization/plans/${encodeURIComponent(planId)}`),
  /** Most recent plan for a (depot_id, delivery_date), or null if none exists yet. */
  findPlan: (depotId: string, deliveryDate: string) =>
    api.get<LoadPlan | null>(`/optimization/plans?depot_id=${encodeURIComponent(depotId)}&delivery_date=${encodeURIComponent(deliveryDate)}`),
  planCsvUrl: (planId: string) => `/api/v1/optimization/plans/${encodeURIComponent(planId)}/export.csv`,

  listPlans: () => api.get<PlanSummary[]>('/plans'),
  listVirtualVehicles: (planId?: string, vehicleType?: string, status?: string) => {
    const params = new URLSearchParams()
    if (planId) params.set('plan_id', planId)
    if (vehicleType) params.set('vehicle_type', vehicleType)
    if (status) params.set('status', status)
    return api.get<VirtualVehicle[]>(`/virtual-vehicles${params.size ? `?${params}` : ''}`)
  },

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
