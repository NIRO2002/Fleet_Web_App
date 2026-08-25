import { afterEach, describe, expect, it, vi } from 'vitest'
import { parcelService } from './parcelService'

afterEach(() => vi.unstubAllGlobals())

describe('parcel planning-instance requests', () => {
  it('uses ISO depot/date filters and pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    await parcelService.listPage('D-CMB-002', '2026-01-05', 50, 0)
    expect(fetchMock.mock.calls[0][0]).toContain('/parcels?depot_id=D-CMB-002&delivery_date=2026-01-05&paginated=true&limit=50&offset=0')
  })

  it('clusters by depot/date without dataset_id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'trained', parcel_count: 400, n_clusters_pre_repair: 4, n_clusters_post_repair: 3, noise_count: 2, unassigned_count: 0, n_singleton_clusters: 1, n_clusters_below_viability: 2, runtime_seconds: 1, repair: { applied: true, n_split: 0, n_merged: 1, excluded_infeasible_count: 0 }, clusters: {} }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    await parcelService.trainClustering('D-CMB-002', '2026-01-05')
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('depot_id=D-CMB-002&delivery_date=2026-01-05')
    expect(url).not.toContain('dataset_id')
  })
})
