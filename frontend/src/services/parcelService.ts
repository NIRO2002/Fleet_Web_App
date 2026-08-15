import { api } from './api'
import type { ClusterPrediction, ClusterSummary, ClusteringTrainResult, CsvUploadResult, Parcel, ParcelInput } from '../types'

export const parcelService = {
  list: () => api.get<Parcel[]>('/parcels'),
  create: (payload: ParcelInput) => api.post<Parcel>('/parcels', payload),

  uploadCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<CsvUploadResult>('/parcels/upload-csv', form)
  },

  trainClustering: () => api.post<ClusteringTrainResult>('/parcels/clustering/train'),
  getClusterSummary: () => api.get<ClusterSummary>('/parcels/clustering'),
  predictCluster: (parcel: ParcelInput) => api.post<ClusterPrediction>('/parcels/clustering/predict', { parcel }),
}
