import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/optimizationService', () => ({ optimizationService: { listJobs: vi.fn() } }))
import { optimizationService } from '../services/optimizationService'
import { OPTIMIZATION_JOBS_CHANGED, OptimizationJobTracker } from './OptimizationJobTracker'
import type { OptimizationJob } from '../types'

const running = { job_id:'JOB-1', status:'RUNNING', job_type:'SINGLE_CLUSTER', batch_id:null, cluster_id:4,
  depot_id:'D-CMB-001', delivery_date:'2026-01-05', parcel_ids:['P1'], progress_percent:20,
  stage:'NSGA-II', message:'NSGA-II optimization is running', plan_id:null, virtual_vehicle_ids:[],
  result_summary:null, error_code:null, error_message:null, created_at:'2026-01-05T00:00:00',
  started_at:null, completed_at:null, updated_at:'2026-01-05T00:00:00' } satisfies OptimizationJob

describe('OptimizationJobTracker', () => {
  beforeEach(()=>{ cleanup(); vi.clearAllMocks() })
  it('recovers active jobs from the backend and notifies on completion', async () => {
    vi.mocked(optimizationService.listJobs)
      .mockResolvedValueOnce([running])
      .mockResolvedValueOnce([{...running,status:'COMPLETED',progress_percent:100,stage:'COMPLETED',message:'Optimization completed',plan_id:'PLAN-1',virtual_vehicle_ids:['VV-1'],result_summary:{n_parcels:1,n_vehicles:1,cluster_id:4}}])
    render(<MemoryRouter><OptimizationJobTracker /></MemoryRouter>)
    expect(await screen.findByText(/Optimization running · 20%/i)).toBeInTheDocument()
    window.dispatchEvent(new Event(OPTIMIZATION_JOBS_CHANGED))
    expect(await screen.findByText('Optimization completed')).toBeInTheDocument()
    expect(screen.getByRole('link', {name:'View Plan'})).toHaveAttribute('href','/load-plans/PLAN-1')
    await waitFor(()=>expect(optimizationService.listJobs).toHaveBeenCalledTimes(2))
  })

  it('keeps tracking independently of the optimization page', async () => {
    vi.mocked(optimizationService.listJobs).mockResolvedValue([running])
    render(<MemoryRouter><div>Parcel Consolidation</div><OptimizationJobTracker /></MemoryRouter>)
    expect(await screen.findByText(/Optimization running · 20%/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Optimization jobs'}))
    expect(screen.getByText(/Cluster 4/)).toBeInTheDocument()
  })
})
