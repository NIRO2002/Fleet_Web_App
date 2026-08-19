import { api } from './api'
import type { ClusterPrediction, ClusterSummary, ClusteringTrainResult, CsvUploadResult, Parcel, ParcelInput } from '../types'

// This frontend has no depot/planning-date selector, but the backend scopes
// clustering (and load optimization, which requires every selected parcel to
// share one non-null depot_id) to a single (depot_id, delivery_date) planning
// instance and never falls back to the whole table. Every parcel this UI
// creates, and every clustering call it makes, uses this one fixed instance
// so the two sides actually line up.
export const DEMO_DEPOT_ID = 'DEPOT-1'
export const demoDeliveryDate = () => new Date().toISOString().slice(0, 10)

const instanceQuery = () => `depot_id=${encodeURIComponent(DEMO_DEPOT_ID)}&delivery_date=${demoDeliveryDate()}`

export const parcelService = {
  list: () => api.get<Parcel[]>('/parcels'),
  create: (payload: ParcelInput) =>
    api.post<Parcel>('/parcels', { ...payload, depot_id: DEMO_DEPOT_ID, delivery_date: demoDeliveryDate() }),

  uploadCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<CsvUploadResult>('/parcels/upload-csv', form)
  },

  trainClustering: () => api.post<ClusteringTrainResult>(`/parcels/clustering/train?${instanceQuery()}`),
  getClusterSummary: () => api.get<ClusterSummary>(`/parcels/clustering?${instanceQuery()}`),
  predictCluster: (parcel: ParcelInput) =>
    api.post<ClusterPrediction>(`/parcels/clustering/predict?${instanceQuery()}`, {
      parcel: { ...parcel, depot_id: DEMO_DEPOT_ID, delivery_date: demoDeliveryDate() },
    }),
}
