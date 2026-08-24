import { api } from './api'
import type { VehicleTypeCatalog, VehicleTypeCatalogInput } from '../types'

export const vehicleTypeService = {
  list: (depotId?: string) => api.get<VehicleTypeCatalog[]>(`/vehicle-types${depotId ? `?depot_id=${encodeURIComponent(depotId)}` : ''}`),
  get: (code: string) => api.get<VehicleTypeCatalog>(`/vehicle-types/${encodeURIComponent(code)}`),
  create: (payload: VehicleTypeCatalogInput) => api.post<VehicleTypeCatalog>('/vehicle-types', payload),
  update: (code: string, payload: VehicleTypeCatalogInput) => api.patch<VehicleTypeCatalog>(`/vehicle-types/${encodeURIComponent(code)}`, payload),
  deactivate: (code: string) => api.del<void>(`/vehicle-types/${encodeURIComponent(code)}`),
}
