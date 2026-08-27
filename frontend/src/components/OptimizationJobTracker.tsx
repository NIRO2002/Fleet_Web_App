import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, LoaderCircle, XCircle } from 'lucide-react'
import { optimizationService } from '../services/optimizationService'
import type { OptimizationJob } from '../types'

export const OPTIMIZATION_JOBS_CHANGED = 'fleet:optimization-jobs-changed'

export function OptimizationJobTracker() {
  const [jobs, setJobs] = useState<OptimizationJob[]>([])
  const [open, setOpen] = useState(false)
  const [notice, setNotice] = useState<OptimizationJob | null>(null)
  const [unreachable, setUnreachable] = useState(false)
  const previous = useRef(new Map<string, string>())
  const failures = useRef(0)

  useEffect(() => {
    let active = true
    let timer = 0
    const poll = async () => {
      try {
        const rows = await optimizationService.listJobs()
        if (!active) return
        failures.current = 0
        setUnreachable(false)
        for (const job of rows) {
          const before = previous.current.get(job.job_id)
          if (before && before !== job.status && (job.status === 'COMPLETED' || job.status === 'FAILED')) setNotice(job)
        }
        previous.current = new Map(rows.map((job) => [job.job_id, job.status]))
        setJobs(rows)
        const hasActive = rows.some((job) => job.status === 'QUEUED' || job.status === 'RUNNING')
        timer = window.setTimeout(poll, hasActive ? 2000 : 10000)
      } catch {
        if (!active) return
        failures.current += 1
        // A couple of misses can be a network blip; beyond that we can no
        // longer vouch for the last snapshot, so stop showing it as live.
        if (failures.current >= 2) {
          previous.current = new Map()
          setJobs([])
          setUnreachable(true)
        }
        timer = window.setTimeout(poll, 10000)
      }
    }
    const refresh = () => { window.clearTimeout(timer); void poll() }
    window.addEventListener(OPTIMIZATION_JOBS_CHANGED, refresh)
    void poll()
    return () => { active = false; window.clearTimeout(timer); window.removeEventListener(OPTIMIZATION_JOBS_CHANGED, refresh) }
  }, [])

  const activeJobs = jobs.filter((job) => job.status === 'QUEUED' || job.status === 'RUNNING')
  const latest = activeJobs[0]
  return <div className="relative">
    <button aria-label="Optimization jobs" className="rounded-xl border border-fleet-line bg-white px-3 py-2 text-left text-xs font-bold shadow-sm" onClick={()=>setOpen(!open)} type="button">
      {unreachable ? <span className="flex items-center gap-2 text-red-700"><XCircle className="h-4 w-4" />Server unreachable</span>
        : latest ? <span className="flex items-center gap-2"><LoaderCircle className="h-4 w-4 animate-spin text-fleet-blue" />{activeJobs.length > 1 ? `${activeJobs.length} optimizations running` : `Optimization ${latest.status.toLowerCase()} · ${latest.progress_percent}%`}</span> : 'Optimization jobs'}
    </button>
    {open&&<div className="absolute right-0 top-12 z-50 w-96 max-w-[85vw] rounded-2xl border bg-white p-4 shadow-2xl"><h3 className="mb-3 font-black">Recent optimization jobs</h3><div className="max-h-80 space-y-3 overflow-auto">{jobs.slice(0,10).map((job)=><div className="rounded-xl border p-3 text-xs" key={job.job_id}><div className="flex justify-between"><b>{job.cluster_id===null?'Parcel set':`Cluster ${job.cluster_id}`}</b><b>{job.status}</b></div><div className="mt-1 text-fleet-muted">{job.stage} · {job.progress_percent}% — {job.message}</div><div className="mt-2 h-1.5 overflow-hidden rounded bg-slate-100"><div className="h-full bg-fleet-blue" style={{width:`${job.progress_percent}%`}} /></div>{job.plan_id&&<Link className="mt-2 inline-block font-black text-fleet-blue" to={`/load-plans/${job.plan_id}`}>View Plan</Link>}{job.status==='FAILED'&&<p className="mt-2 text-red-700">{job.error_message}</p>}</div>)}</div></div>}
    {notice&&<div className={`fixed bottom-5 right-5 z-50 max-w-sm rounded-2xl border bg-white p-4 shadow-2xl ${notice.status==='FAILED'?'border-red-200':'border-green-200'}`} role="status"><button aria-label="Dismiss notification" className="float-right" onClick={()=>setNotice(null)}>×</button><div className="flex gap-2 font-black">{notice.status==='COMPLETED'?<CheckCircle2 className="text-green-600"/>:<XCircle className="text-red-600"/>}Optimization {notice.status.toLowerCase()}</div><p className="mt-2 text-sm">{notice.status==='COMPLETED'?`${notice.result_summary?.n_vehicles??0} virtual vehicles created`:notice.error_message}</p>{notice.plan_id&&<Link className="mt-3 inline-block font-black text-fleet-blue" to={`/load-plans/${notice.plan_id}`}>View Plan</Link>}</div>}
  </div>
}
