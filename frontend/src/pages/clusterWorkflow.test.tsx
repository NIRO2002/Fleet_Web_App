import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

vi.mock('../services/parcelService', () => ({ parcelService: {
  getClusterSummary: vi.fn(), listDepots: vi.fn(), priorityLevels: vi.fn(), serviceTypes: vi.fn(),
  listPage: vi.fn(), listForInstance: vi.fn(), trainClustering: vi.fn(), create: vi.fn(), uploadCsv: vi.fn(),
} }))
vi.mock('../services/optimizationService', () => ({ optimizationService: {
  run: vi.fn(), listVirtualVehicles: vi.fn(), insertParcel: vi.fn(),
} }))
vi.mock('../services/vehicleTypeService', () => ({ vehicleTypeService: { list: vi.fn() } }))

import { LoadOptimizationPage } from './LoadOptimizationPage'
import { ParcelConsolidationPage } from './ParcelConsolidationPage'
import { parcelService } from '../services/parcelService'
import { optimizationService } from '../services/optimizationService'
import { vehicleTypeService } from '../services/vehicleTypeService'

const parcelMock = vi.mocked(parcelService)
const optimizationMock = vi.mocked(optimizationService)
const vehicleTypeMock = vi.mocked(vehicleTypeService)

beforeEach(() => {
  cleanup()
  sessionStorage.clear()
  vi.clearAllMocks()
  parcelMock.getClusterSummary.mockResolvedValue({ '0': 45, '4': 60, '-1': 6 })
  parcelMock.listDepots.mockResolvedValue([{ depot_id: 'D-CMB-001', depot_name: 'Central', lat: 6.927, lng: 79.861 }])
  parcelMock.priorityLevels.mockResolvedValue({ standard: 0 })
  parcelMock.serviceTypes.mockResolvedValue(['door_to_door'])
  parcelMock.listPage.mockResolvedValue({ items: [], total: 105, limit: 50, offset: 0 })
  parcelMock.listForInstance.mockResolvedValue([])
  optimizationMock.listVirtualVehicles.mockResolvedValue([])
  vehicleTypeMock.list.mockResolvedValue([])
})

function renderOptimization(state: object) {
  return render(<MemoryRouter initialEntries={[{ pathname: '/load-optimization', state }]}>
    <Routes><Route element={<LoadOptimizationPage />} path="/load-optimization" /></Routes>
  </MemoryRouter>)
}

describe('cluster optimization workflow', () => {
  it('loads scoped clusters, excludes noise, prioritizes and preselects clusterId', async () => {
    renderOptimization({ clusterId: 4, clusterIds: [0, 4], depotId: 'D-CMB-001', deliveryDate: '2026-01-05' })

    expect(await screen.findByRole('option', { name: /Cluster 4.*60 parcels/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Cluster 0.*45 parcels/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /noise|Cluster -1/i })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /Cluster/i })).toHaveValue('4')
    expect(parcelMock.getClusterSummary).toHaveBeenCalledWith('D-CMB-001', '2026-01-05')
    expect(screen.getByRole('button', { name: 'By Cluster' })).toHaveClass('bg-white')
  })

  it('reports cluster-summary loading failures', async () => {
    parcelMock.getClusterSummary.mockRejectedValue(new Error('Cluster API unavailable'))
    renderOptimization({ depotId: 'D-CMB-001', deliveryDate: '2026-01-05' })
    expect(await screen.findByText('Cluster API unavailable')).toBeInTheDocument()
  })

  it('sends the complete planning-instance scope for By Cluster optimization', async () => {
    optimizationMock.run.mockImplementation(() => new Promise(() => {}))
    renderOptimization({ clusterId: 4, depotId: 'D-CMB-001', deliveryDate: '2026-01-05' })
    await screen.findByRole('option', { name: /Cluster 4/ })
    fireEvent.click(screen.getByRole('button', { name: /Run NSGA-II Optimization/ }))
    await waitFor(() => expect(optimizationMock.run).toHaveBeenCalled())
    expect(optimizationMock.run).toHaveBeenCalledWith(expect.objectContaining({
      cluster_id: 4, depot_id: 'D-CMB-001', delivery_date: '2026-01-05',
      depot_latitude: expect.any(Number), depot_longitude: expect.any(Number),
    }))
  })

  it('keeps All Clusters mode and removes invalid cluster ids', async () => {
    renderOptimization({ clusterIds: [0, 4, -1], depotId: 'D-CMB-001', deliveryDate: '2026-01-05' })
    expect(await screen.findByText('Clusters to optimize (2)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All Clusters' })).toHaveClass('bg-white')
  })

  it('navigates from a valid snapshot cluster with exact scope and no noise button', async () => {
    function Probe() { const location = useLocation(); return <pre data-testid="location">{JSON.stringify(location.state)}</pre> }
    render(<MemoryRouter initialEntries={['/parcel-consolidation']}><Routes>
      <Route element={<ParcelConsolidationPage />} path="/parcel-consolidation" />
      <Route element={<Probe />} path="/load-optimization" />
    </Routes></MemoryRouter>)

    const cluster4 = await screen.findByText('Cluster 4')
    const noiseRow = screen.getByText('Unassigned (noise)').parentElement!
    expect(within(noiseRow).queryByRole('button', { name: 'Optimize' })).not.toBeInTheDocument()
    fireEvent.click(within(cluster4.parentElement!).getByRole('button', { name: 'Optimize' }))
    expect(await screen.findByTestId('location')).toHaveTextContent(
      JSON.stringify({ clusterId: 4, depotId: 'D-CMB-001', deliveryDate: '2026-01-05' }),
    )
  })
})
