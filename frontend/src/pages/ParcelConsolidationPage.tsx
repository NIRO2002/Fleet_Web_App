import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, Boxes, PackagePlus, Sparkles, Upload, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Card, DataTable, EmptyState, InlineAlert, LoadingState, MetricCard, PageHeader, PrimaryButton, SecondaryButton, StatusBadge } from '../components/UI'
import { CSV_TEMPLATE_COLUMNS } from '../data/mockData'
import { ApiError } from '../services/api'
import { parcelService } from '../services/parcelService'
import type { ClusterSummary, Depot, Parcel, ParcelDraft } from '../types'
import { clusterColor, clusterLabel, emptyParcelDraft, formatKg, formatM3, formatNumber, nextParcelId, normalizePositions, parcelDraftToInput, parseClusterKey } from '../utils/format'

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null
const PAGE_SIZE = 50

export function ParcelConsolidationPage() {
  const navigate = useNavigate()
  const [depots, setDepots] = useState<Depot[]>([])
  const [selectedDepot, setSelectedDepot] = useState('')
  const [selectedDate, setSelectedDate] = useState('2026-01-05')
  const [parcels, setParcels] = useState<Parcel[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [clusterSummary, setClusterSummary] = useState<ClusterSummary>({})
  const [clusterMetrics, setClusterMetrics] = useState<Record<string, { weight: number; volume: number }>>({})
  const [notice, setNotice] = useState<Notice>(null)
  const [training, setTraining] = useState(false)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvUploading, setCsvUploading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [draft, setDraft] = useState<ParcelDraft>(() => emptyParcelDraft())
  const [priorities, setPriorities] = useState<string[]>([])
  const [serviceTypes, setServiceTypes] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [idError, setIdError] = useState('')

  const loadPage = useCallback(async () => {
    if (!selectedDepot || !selectedDate) { setParcels([]); setTotal(0); setLoading(false); return }
    setLoading(true)
    try {
      const [page, clusters] = await Promise.all([
        parcelService.listPage(selectedDepot, selectedDate, PAGE_SIZE, offset),
        parcelService.getClusterSummary(selectedDepot, selectedDate).catch(() => ({})),
      ])
      setParcels(page.items); setTotal(page.total); setClusterSummary(clusters)
      if (Object.keys(clusters).length) {
        const all = await parcelService.listForInstance(selectedDepot, selectedDate)
        setClusterMetrics(all.reduce<Record<string, {weight:number;volume:number}>>((out,p)=>{const key=String(p.cluster_id);const row=out[key]??{weight:0,volume:0};row.weight+=p.weight_kg;row.volume+=p.volume_m3;out[key]=row;return out},{}))
      } else setClusterMetrics({})
    } catch (err) { setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to load parcels.' }) }
    finally { setLoading(false) }
  }, [selectedDepot, selectedDate, offset])

  useEffect(() => {
    Promise.all([parcelService.listDepots(), parcelService.priorityLevels(), parcelService.serviceTypes()]).then(([depotRows, priorityMap, services]) => {
      setDepots(depotRows); setPriorities(Object.keys(priorityMap)); setServiceTypes(services)
      setSelectedDepot((current) => current || depotRows[0]?.depot_id || '')
    }).catch((err) => setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to load filter options.' }))
  }, [])
  useEffect(() => { const timer = window.setTimeout(() => void loadPage(), 0); return () => window.clearTimeout(timer) }, [loadPage])

  const openModal = () => {
    setDraft({ ...emptyParcelDraft(nextParcelId(parcels.map((p) => p.parcel_id))), depot_id: selectedDepot, delivery_date: selectedDate, priority_level: priorities[0] ?? 'standard', service_type: serviceTypes.includes('door_to_door') ? 'door_to_door' : serviceTypes[0] ?? '' })
    setFormError(''); setIdError(''); setModalOpen(true)
  }
  const submitParcel = async (event: FormEvent) => {
    event.preventDefault(); setFormError(''); setIdError('')
    try {
      const payload = parcelDraftToInput(draft)
      setSubmitting(true); await parcelService.create(payload)
      setModalOpen(false); setNotice({ tone: 'success', text: `Parcel ${payload.parcel_id} added.` }); setOffset(0); await loadPage()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setIdError('Parcel ID already exists')
      else setFormError(err instanceof Error ? err.message : 'Failed to add parcel.')
    } finally { setSubmitting(false) }
  }
  const uploadCsv = async () => {
    if (!csvFile || !selectedDepot || !selectedDate) return
    setCsvUploading(true)
    try { const result = await parcelService.uploadCsv(csvFile, selectedDepot, selectedDate); setCsvFile(null); setNotice({ tone: 'success', text: `CSV processed ${result.processed} rows (${result.inserted} inserted, ${result.updated} updated).` }); setOffset(0); await loadPage() }
    catch (err) { setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'CSV upload failed.' }) }
    finally { setCsvUploading(false) }
  }
  const runClustering = async () => {
    if (!selectedDepot || !selectedDate || total === 0) return
    setTraining(true); setNotice({ tone: 'info', text: `Running HDBSCAN on ${total} parcels for ${selectedDepot} on ${selectedDate}...` })
    try { const result = await parcelService.trainClustering(selectedDepot, selectedDate); setNotice({ tone: 'success', text: `Clustered ${result.parcel_count} parcels into ${result.n_clusters ?? Object.keys(result.clusters).length} clusters.` }); await loadPage() }
    catch (err) { setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Clustering failed.' }) }
    finally { setTraining(false) }
  }

  const clusterRows = Object.entries(clusterSummary).map(([key, count]) => ({ id: parseClusterKey(key), count }))
  const positions = useMemo(() => normalizePositions(parcels), [parcels])
  const clustered = Object.entries(clusterSummary).filter(([key]) => Number(key) >= 0).reduce((sum, [, count]) => sum + count, 0)
  const noise = clusterSummary['-1'] ?? 0
  const dimensionWarning = (() => { const l=Number(draft.length_cm),w=Number(draft.width_cm),h=Number(draft.height_cm),v=Number(draft.volume_m3); if (![l,w,h,v].every((n)=>n>0)) return ''; const implied=l*w*h/1e6; return Math.abs(implied-v)/v>0.05 ? `Dimensions imply ${implied.toFixed(4)} m³, more than 5% from entered volume.` : '' })()

  return <div>
    <PageHeader description="Filter one planning instance, manage its parcels, and run HDBSCAN clustering." title="Parcel Consolidation" />
    {notice && <div className="mb-5"><InlineAlert tone={notice.tone}>{notice.text}</InlineAlert></div>}
    <Card className="mb-5" title="Filters"><div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm font-bold">Depot<select className="mt-1 block w-full rounded-xl border border-fleet-line px-3 py-2.5" value={selectedDepot} onChange={(e)=>{setSelectedDepot(e.target.value);setOffset(0);setClusterSummary({})}}><option value="">Select depot</option>{depots.map((d)=><option key={d.depot_id} value={d.depot_id}>{d.depot_id} — {d.depot_name}</option>)}</select></label>
      <label className="text-sm font-bold">Delivery Date<input className="mt-1 block w-full rounded-xl border border-fleet-line px-3 py-2.5" type="date" value={selectedDate} onChange={(e)=>{setSelectedDate(e.target.value);setOffset(0);setClusterSummary({})}} /></label>
    </div></Card>
    <div className="mb-5 grid gap-4 sm:grid-cols-3"><MetricCard icon={Boxes} label="Total Parcels" tone="blue" value={formatNumber(total)} /><MetricCard icon={Sparkles} label="Clustered" tone="green" value={formatNumber(clustered)} /><MetricCard icon={Boxes} label="Noise" tone="amber" value={formatNumber(noise)} /></div>
    <div className="grid gap-5 xl:grid-cols-[1.6fr_0.9fr]">
      <Card title="Parcel Intake" action={<PrimaryButton onClick={openModal}><PackagePlus className="h-4 w-4" /> Add Parcel</PrimaryButton>}>
        <h3 className="mb-1 text-sm font-extrabold">Bulk import via CSV</h3><p className="mb-3 text-xs text-fleet-muted">Columns: {CSV_TEMPLATE_COLUMNS.join(', ')}</p>
        <div className="flex flex-wrap gap-3"><label className="cursor-pointer rounded-xl border px-4 py-2.5 text-sm font-bold"><Upload className="mr-2 inline h-4 w-4" />{csvFile?.name ?? 'Choose CSV file'}<input accept=".csv" className="hidden" type="file" onChange={(e)=>setCsvFile(e.target.files?.[0]??null)} /></label><PrimaryButton disabled={!csvFile || !selectedDepot || !selectedDate} loading={csvUploading} onClick={uploadCsv}>Upload</PrimaryButton></div>
      </Card>
      <Card title="Cluster Snapshot" action={<StatusBadge tone="blue">{clusterRows.filter((r)=>r.id!==null&&r.id>=0).length} clusters</StatusBadge>}>
        <div className="map-grid relative mb-4 h-48 overflow-hidden rounded-2xl border border-slate-300">{positions.map((pos,i)=><span className="absolute h-2.5 w-2.5 rounded-full ring-2 ring-white" key={parcels[i].parcel_id} style={{left:`${pos.left}%`,top:`${pos.top}%`,background:clusterColor(parcels[i].cluster_id)}} title={`${parcels[i].parcel_id} · ${clusterLabel(parcels[i].cluster_id)}`} />)}</div>
        <PrimaryButton disabled={!selectedDepot || !selectedDate || total===0} loading={training} onClick={runClustering}><Sparkles className="h-4 w-4" /> Run HDBSCAN Clustering</PrimaryButton><span className="ml-3 text-xs font-bold text-fleet-muted">{total} parcels in scope</span>
        {total===0 && <p className="mt-3 text-sm text-amber-700">No parcels match this depot and date.</p>}
        <div className="mt-4 space-y-2">{clusterRows.map((r)=><div className="flex justify-between gap-3 text-sm" key={String(r.id)}><span>{clusterLabel(r.id)}</span><span><b>{r.count}</b> · {formatKg(clusterMetrics[String(r.id)]?.weight??0)} · {formatM3(clusterMetrics[String(r.id)]?.volume??0)}</span></div>)}</div>
        {clustered>0 && <div className="mt-4"><PrimaryButton onClick={()=>navigate('/load-optimization',{state:{clusterIds:clusterRows.filter((r)=>r.id!==null&&r.id>=0).map((r)=>r.id)}})} >Continue to Optimization <ArrowRight className="h-4 w-4" /></PrimaryButton></div>}
      </Card>
    </div>
    <Card className="mt-5" title={`Parcels — ${total} matching`}>
      {loading ? <LoadingState message="Loading filtered parcels..." /> : parcels.length===0 ? <EmptyState icon={Boxes} title="No parcels found" description="Change the filters, add a parcel, or upload a CSV." /> : <DataTable headers={['Parcel ID','Depot','Delivery Date','Weight','Volume','Location','Dimensions','Window','Priority','Status','Cluster']}><>{parcels.map((p)=><tr key={p.parcel_id}><td className="px-4 py-3 font-bold">{p.parcel_id}</td><td className="px-4 py-3">{p.depot_id}</td><td className="px-4 py-3">{p.delivery_date}</td><td className="px-4 py-3">{formatKg(p.weight_kg)}</td><td className="px-4 py-3">{formatM3(p.volume_m3)}</td><td className="px-4 py-3">{p.latitude.toFixed(4)}, {p.longitude.toFixed(4)}</td><td className="px-4 py-3">{p.length_cm ? `${p.length_cm}×${p.width_cm}×${p.height_cm} cm` : '—'}</td><td className="px-4 py-3">{p.time_window_start}–{p.time_window_end}</td><td className="px-4 py-3">{p.priority_level}</td><td className="px-4 py-3"><StatusBadge tone={p.status==='PENDING'?'amber':'blue'}>{p.status}</StatusBadge></td><td className="px-4 py-3">{clusterLabel(p.cluster_id)}</td></tr>)}</></DataTable>}
      <div className="mt-4 flex items-center justify-between"><SecondaryButton disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-PAGE_SIZE))}>Previous</SecondaryButton><span className="text-sm font-bold">{total ? offset+1 : 0}–{Math.min(offset+PAGE_SIZE,total)} of {total}</span><SecondaryButton disabled={offset+PAGE_SIZE>=total} onClick={()=>setOffset(offset+PAGE_SIZE)}>Next</SecondaryButton></div>
    </Card>
    {modalOpen && <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/60 p-4" onClick={()=>setModalOpen(false)}><div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white shadow-2xl" onClick={(e)=>e.stopPropagation()}><div className="flex items-center justify-between border-b px-5 py-4"><h2 className="font-extrabold">Add Parcel</h2><button aria-label="Close" onClick={()=>setModalOpen(false)}><X className="h-5 w-5" /></button></div><form className="space-y-5 p-5" onSubmit={submitParcel}>
      {formError && <InlineAlert tone="error">{formError}</InlineAlert>}<Section title="Basic Information"><Input label="Parcel ID *" value={draft.parcel_id} onChange={(v)=>setDraft({...draft,parcel_id:v})} error={idError}/><Input label="Dataset ID" value={draft.dataset_id} onChange={(v)=>setDraft({...draft,dataset_id:v})}/><Select label="Depot *" value={draft.depot_id} onChange={(v)=>setDraft({...draft,depot_id:v})} options={depots.map((d)=>[d.depot_id,`${d.depot_id} — ${d.depot_name}`])}/><Input label="Delivery Date *" type="date" value={draft.delivery_date} onChange={(v)=>setDraft({...draft,delivery_date:v})}/></Section>
      <Section title="Location"><Input label="Latitude *" type="number" value={draft.latitude} onChange={(v)=>setDraft({...draft,latitude:v})}/><Input label="Longitude *" type="number" value={draft.longitude} onChange={(v)=>setDraft({...draft,longitude:v})}/></Section>
      <Section title="Package Size"><Input label="Weight (kg) *" type="number" value={draft.weight_kg} onChange={(v)=>setDraft({...draft,weight_kg:v})}/><Input label="Volume (m³) *" type="number" value={draft.volume_m3} onChange={(v)=>setDraft({...draft,volume_m3:v})}/><Input label="Length (cm)" type="number" value={draft.length_cm} onChange={(v)=>setDraft({...draft,length_cm:v})}/><Input label="Width (cm)" type="number" value={draft.width_cm} onChange={(v)=>setDraft({...draft,width_cm:v})}/><Input label="Height (cm)" type="number" value={draft.height_cm} onChange={(v)=>setDraft({...draft,height_cm:v})}/>{dimensionWarning&&<p className="text-xs text-amber-700">{dimensionWarning}</p>}</Section>
      <Section title="Delivery"><Input label="Start *" type="time" value={draft.time_window_start} onChange={(v)=>setDraft({...draft,time_window_start:v})}/><Input label="End *" type="time" value={draft.time_window_end} onChange={(v)=>setDraft({...draft,time_window_end:v})}/><Select label="Priority" value={draft.priority_level} onChange={(v)=>setDraft({...draft,priority_level:v})} options={priorities.map((v)=>[v,v])}/><Select label="Service Type" value={draft.service_type} onChange={(v)=>setDraft({...draft,service_type:v})} options={serviceTypes.map((v)=>[v,v])}/></Section>
      <Section title="Handling"><Checks draft={draft} setDraft={setDraft}/><Input label="Max Stack Weight (kg)" type="number" value={draft.max_stack_weight_kg} onChange={(v)=>setDraft({...draft,max_stack_weight_kg:v})}/></Section>
      <Section title="Special Cargo"><Check label="Hazardous" checked={draft.hazardous} onChange={(v)=>setDraft({...draft,hazardous:v,hazmat_class:v?draft.hazmat_class:''})}/><Input disabled={!draft.hazardous} label="Hazmat Class" value={draft.hazmat_class} onChange={(v)=>setDraft({...draft,hazmat_class:v})}/><Check label="Requires Refrigeration" checked={draft.requires_refrigeration} onChange={(v)=>setDraft({...draft,requires_refrigeration:v,temp_min_celsius:v?draft.temp_min_celsius:'',temp_max_celsius:v?draft.temp_max_celsius:''})}/><Input disabled={!draft.requires_refrigeration} label="Minimum °C" type="number" value={draft.temp_min_celsius} onChange={(v)=>setDraft({...draft,temp_min_celsius:v})}/><Input disabled={!draft.requires_refrigeration} label="Maximum °C" type="number" value={draft.temp_max_celsius} onChange={(v)=>setDraft({...draft,temp_max_celsius:v})}/></Section>
      <div className="flex justify-end gap-2 border-t pt-4"><SecondaryButton onClick={()=>setModalOpen(false)}>Cancel</SecondaryButton><PrimaryButton loading={submitting} type="submit"><PackagePlus className="h-4 w-4" /> Add Parcel</PrimaryButton></div>
    </form></div></div>}
  </div>
}

function Section({title,children}:{title:string;children:React.ReactNode}){return <fieldset><legend className="mb-2 text-sm font-black uppercase text-fleet-muted">{title}</legend><div className="grid gap-3 sm:grid-cols-2">{children}</div></fieldset>}
function Input({label,value,onChange,type='text',disabled=false,error=''}:{label:string;value:string;onChange:(v:string)=>void;type?:string;disabled?:boolean;error?:string}){return <label className="text-sm font-bold">{label}<input disabled={disabled} className={`mt-1 block w-full rounded-xl border px-3 py-2 ${error?'border-red-500':'border-fleet-line'}`} step={type==='number'?'any':undefined} type={type} value={value} onChange={(e)=>onChange(e.target.value)}/>{error&&<span className="text-xs text-red-600">{error}</span>}</label>}
function Select({label,value,onChange,options}:{label:string;value:string;onChange:(v:string)=>void;options:string[][]}){return <label className="text-sm font-bold">{label}<select className="mt-1 block w-full rounded-xl border px-3 py-2" value={value} onChange={(e)=>onChange(e.target.value)}>{options.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>}
function Check({label,checked,onChange}:{label:string;checked:boolean;onChange:(v:boolean)=>void}){return <label className="flex items-center gap-2 text-sm font-bold"><input checked={checked} type="checkbox" onChange={(e)=>onChange(e.target.checked)}/>{label}</label>}
function Checks({draft,setDraft}:{draft:ParcelDraft;setDraft:(d:ParcelDraft)=>void}){return <><Check label="Fragile" checked={draft.fragile} onChange={(v)=>setDraft({...draft,fragile:v,stackable:v?false:draft.stackable})}/><Check label="Stackable" checked={draft.stackable} onChange={(v)=>setDraft({...draft,stackable:v})}/><Check label="Fixed loading orientation" checked={draft.loading_orientation_fixed} onChange={(v)=>setDraft({...draft,loading_orientation_fixed:v})}/><Check label="Two-person lift" checked={draft.two_person_lift} onChange={(v)=>setDraft({...draft,two_person_lift:v})}/><Check label="Do not tilt" checked={draft.do_not_tilt} onChange={(v)=>setDraft({...draft,do_not_tilt:v})}/></>}
