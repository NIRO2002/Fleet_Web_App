import { api } from './api'
import type { ClusterPrediction, ClusterSummary, ClusteringTrainResult, CsvUploadResult, Depot, PaginatedParcels, Parcel, ParcelInput } from '../types'

const scope = (depotId: string, deliveryDate: string) => `depot_id=${encodeURIComponent(depotId)}&delivery_date=${encodeURIComponent(deliveryDate)}`

export const parcelService = {
  listForInstance: (depotId: string, deliveryDate: string) => api.get<Parcel[]>(`/parcels?${scope(depotId, deliveryDate)}`),
  listPage: (depotId: string, deliveryDate: string, limit: number, offset: number) => api.get<PaginatedParcels>(`/parcels?${scope(depotId, deliveryDate)}&paginated=true&limit=${limit}&offset=${offset}`),
  listForDataset: (datasetId: string) => api.get<Parcel[]>(`/parcels?dataset_id=${encodeURIComponent(datasetId)}`),
  create: (payload: ParcelInput) => api.post<Parcel>('/parcels', payload),
  uploadCsv: (file: File, depotId: string, deliveryDate: string) => {
    const form = new FormData(); form.append('file', file)
    return api.postForm<CsvUploadResult>(`/parcels/upload-csv?${scope(depotId, deliveryDate)}`, form)
  },
  trainClustering: (depotId: string, deliveryDate: string) => api.post<ClusteringTrainResult>(`/parcels/clustering/train?${scope(depotId, deliveryDate)}`),
  getClusterSummary: (depotId: string, deliveryDate: string) => api.get<ClusterSummary>(`/parcels/clustering?${scope(depotId, deliveryDate)}`),
  listUnassigned: (depotId: string, deliveryDate: string) => api.get<Parcel[]>(`/parcels/clustering/unassigned?${scope(depotId, deliveryDate)}`),
  predictCluster: (parcel: ParcelInput) => api.post<ClusterPrediction>(`/parcels/clustering/predict?${scope(parcel.depot_id ?? '', parcel.delivery_date ?? '')}`, { parcel }),
  listDepots: () => api.get<Depot[]>('/depots'),
  priorityLevels: () => api.get<Record<string, number>>('/vocabularies/priority-levels'),
  serviceTypes: () => api.get<string[]>('/vocabularies/service-types'),
}
