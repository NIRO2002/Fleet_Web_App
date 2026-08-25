import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, PackageOpen, View } from 'lucide-react'
import { Card, EmptyState, InlineAlert, LoadingState, PageHeader, PrimaryButton, SecondaryButton, StatusBadge } from '../components/UI'
import { CargoBay3D } from '../components/CargoBay3D'
import { optimizationService } from '../services/optimizationService'
import { vehicleTypeService } from '../services/vehicleTypeService'
import type { LoadPlan, LoadPlanVehicle, PlanSummary, VehicleTypeCatalog } from '../types'
import { formatKg, formatM3, formatNumber, formatPercent } from '../utils/format'
import { readSession, writeSession } from '../utils/sessionStore'

export function LoadedVehiclesPage() {
  const navigate = useNavigate()
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [types, setTypes] = useState<VehicleTypeCatalog[]>([])
  const [planId, setPlanId] = useState(() => readSession('loadedVehicles.planId', ''))
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [utilization, setUtilization] = useState('all')
  const [plan, setPlan] = useState<LoadPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState<Set<string>>(new Set())
  const [viewing, setViewing] = useState<LoadPlanVehicle | null>(null)
  const [showIds, setShowIds] = useState(false)

  useEffect(() => {
    Promise.all([optimizationService.listPlans(), vehicleTypeService.list()]).then(([planRows, typeRows]) => {
      setPlans(planRows); setTypes(typeRows); setPlanId((current) => current && planRows.some((p)=>p.plan_id===current) ? current : planRows[0]?.plan_id ?? '')
    }).catch((err)=>setNotice(err instanceof Error?err.message:'Failed to load filters.')).finally(()=>setLoading(false))
  }, [])
  useEffect(() => {
    writeSession('loadedVehicles.planId', planId)
    if (!planId) return
    const timer = window.setTimeout(() => {
      setLoading(true)
      optimizationService.getPlan(planId).then(setPlan).catch((err)=>setNotice(err instanceof Error?err.message:'Failed to load plan.')).finally(()=>setLoading(false))
    }, 0)
    return () => window.clearTimeout(timer)
  }, [planId])

  const statuses = useMemo(()=>Array.from(new Set(plan?.vehicles.map((v)=>v.status)??[])).sort(),[plan])
  const vehicles = useMemo(()=>plan?.vehicles.filter((v)=>(!typeFilter||v.vehicle_type===typeFilter)&&(!statusFilter||v.status===statusFilter)&&(utilization==='all'||(utilization==='under'?v.utilization<0.7:v.utilization>=0.7)))??[],[plan,typeFilter,statusFilter,utilization])
  const markReady = async (vehicle: LoadPlanVehicle) => {
    setPending((old)=>new Set(old).add(vehicle.virtual_vehicle_id)); const original=vehicle
    setPlan((old)=>old&&({...old,vehicles:old.vehicles.map((v)=>v.virtual_vehicle_id===vehicle.virtual_vehicle_id?{...v,status:'READY',ready_at:new Date().toISOString()}:v)}))
    try { await optimizationService.markReady(vehicle.virtual_vehicle_id) } catch(err){setPlan((old)=>old&&({...old,vehicles:old.vehicles.map((v)=>v.virtual_vehicle_id===original.virtual_vehicle_id?original:v)}));setNotice(err instanceof Error?err.message:'Failed to mark READY.')}
    finally { setPending((old)=>{const n=new Set(old);n.delete(vehicle.virtual_vehicle_id);return n}) }
  }
  const ready = plan?.vehicles.filter((v)=>v.status==='READY').length??0

  return <div><PageHeader title="Loaded Vehicles" description="Vehicles are physically loaded, then marked READY." />
    {notice&&<div className="mb-5"><InlineAlert tone="error">{notice}</InlineAlert></div>}
    <Card className="mb-5" title="Vehicle Filters"><div className="grid gap-4 md:grid-cols-4">
      <label className="text-sm font-bold">Plan<select className="mt-1 block w-full rounded-xl border px-3 py-2.5" value={planId} onChange={(e)=>setPlanId(e.target.value)}><option value="">Select plan</option>{plans.map((p)=><option key={p.plan_id} value={p.plan_id}>{p.depot_id} · {p.delivery_date} · {p.plan_id}</option>)}</select></label>
      <label className="text-sm font-bold">Vehicle Type<select className="mt-1 block w-full rounded-xl border px-3 py-2.5" value={typeFilter} onChange={(e)=>setTypeFilter(e.target.value)}><option value="">All types</option>{types.map((t)=><option key={t.code} value={t.code}>{t.display_name}</option>)}</select></label>
      <label className="text-sm font-bold">Status<select className="mt-1 block w-full rounded-xl border px-3 py-2.5" value={statusFilter} onChange={(e)=>setStatusFilter(e.target.value)}><option value="">All statuses</option>{statuses.map((s)=><option key={s}>{s}</option>)}</select></label>
      <label className="text-sm font-bold">Utilization<select className="mt-1 block w-full rounded-xl border px-3 py-2.5" value={utilization} onChange={(e)=>setUtilization(e.target.value)}><option value="all">All utilization</option><option value="under">Under 70%</option><option value="over">70% and over</option></select></label>
    </div></Card>
    {loading?<LoadingState message="Loading existing optimized vehicles..."/>:!plan?<EmptyState icon={PackageOpen} title="No load plan selected" description="Complete Parcel Consolidation and Load Optimization first." action={<PrimaryButton onClick={()=>navigate('/parcel-consolidation')}>Go to Parcel Consolidation</PrimaryButton>}/>:<><div className="mb-5 grid gap-3 sm:grid-cols-4"><Summary label="Vehicles shown" value={`${vehicles.length} / ${plan.n_vehicles}`}/><Summary label="Ready" value={`${ready} / ${plan.n_vehicles}`}/><Summary label="Mean utilization" value={formatPercent(plan.mean_utilization)}/><Summary label="Parcels" value={formatNumber(plan.n_parcels)}/></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{vehicles.map((v)=><VehicleCard key={v.virtual_vehicle_id} vehicle={v} pending={pending.has(v.virtual_vehicle_id)} onReady={()=>markReady(v)} onView={()=>{setShowIds(false);setViewing(v)}}/>)}</div></>}
    {viewing&&<div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/60 p-4" onClick={()=>setViewing(null)}><div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl bg-white p-5" onClick={(e)=>e.stopPropagation()}><div className="mb-4 flex justify-between"><h2 className="font-extrabold">{viewing.virtual_vehicle_id}</h2><SecondaryButton onClick={()=>setViewing(null)}>Close</SecondaryButton></div><label className="mb-3 flex justify-end gap-2"><input type="checkbox" checked={showIds} onChange={(e)=>setShowIds(e.target.checked)}/>Show Parcel IDs</label><CargoBay3D vehicle={viewing} mode="sequence" maxLoadSequence={viewing.parcels.length} showParcelIds={showIds}/></div></div>}
  </div>
}
function Summary({label,value}:{label:string;value:string}){return <div className="rounded-2xl border bg-white p-4"><div className="text-xs font-black uppercase text-fleet-muted">{label}</div><div className="mt-1 text-xl font-black">{value}</div></div>}
function VehicleCard({vehicle,pending,onReady,onView}:{vehicle:LoadPlanVehicle;pending:boolean;onReady:()=>void;onView:()=>void}){const ready=vehicle.status==='READY';return <div className="rounded-2xl border bg-white p-5"><div className="mb-3 flex justify-between"><div><b>{vehicle.virtual_vehicle_id}</b><div className="text-xs text-fleet-muted">{vehicle.vehicle_type}</div></div><StatusBadge tone={ready?'green':'amber'}>{vehicle.status}</StatusBadge></div><div className="grid grid-cols-2 gap-3 text-sm"><span>Parcels<br/><b>{vehicle.parcel_count}</b></span><span>Utilization<br/><b>{formatPercent(vehicle.utilization)}</b></span><span>Weight<br/><b>{formatKg(vehicle.used_weight_kg)}</b></span><span>Volume<br/><b>{formatM3(vehicle.used_volume_m3)}</b></span></div><div className="mt-4 flex justify-between border-t pt-4"><SecondaryButton onClick={onView}><View className="h-4 w-4"/>View 3D Load</SecondaryButton>{ready?<span className="text-sm font-bold text-green-700">READY</span>:<PrimaryButton loading={pending} onClick={onReady}><CheckCircle2 className="h-4 w-4"/>Ready</PrimaryButton>}</div></div>}
