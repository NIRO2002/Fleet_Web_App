import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Boxes, Layers, PackagePlus, RefreshCw, SlidersHorizontal, Sparkles, Target, Upload } from 'lucide-react'
import {
  Card,
  DataTable,
  EmptyState,
  InlineAlert,
  MetricCard,
  PageHeader,
  ParcelFieldsFieldset,
  PrimaryButton,
  SecondaryButton,
  StatusBadge,
} from '../components/UI'
import { CSV_TEMPLATE_COLUMNS } from '../data/mockData'
import { parcelService } from '../services/parcelService'
import type { ClusterPrediction, ClusterSummary, Parcel, ParcelDraft } from '../types'
import {
  clusterColor,
  clusterLabel,
  clusterTone,
  emptyParcelDraft,
  formatNumber,
  formatPercent,
  nextParcelId,
  normalizePositions,
  parcelDraftToInput,
  parseClusterKey,
} from '../utils/format'

type Notice = { tone: 'success' | 'error' | 'info'; text: string } | null

export function ParcelConsolidationPage() {
  const navigate = useNavigate()

  const [parcels, setParcels] = useState<Parcel[]>([])
  const [clusterSummary, setClusterSummary] = useState<ClusterSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [pageNotice, setPageNotice] = useState<Notice>(null)

  const [addDraft, setAddDraft] = useState<ParcelDraft>(() => emptyParcelDraft('P001'))
  const [addSubmitting, setAddSubmitting] = useState(false)
  const [addNotice, setAddNotice] = useState<Notice>(null)

  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvUploading, setCsvUploading] = useState(false)
  const [csvNotice, setCsvNotice] = useState<Notice>(null)

  const [training, setTraining] = useState(false)
  const [trainNotice, setTrainNotice] = useState<Notice>(null)

  const [predictDraft, setPredictDraft] = useState<ParcelDraft>(() => emptyParcelDraft('NEW-1'))
  const [predicting, setPredicting] = useState(false)
  const [predictNotice, setPredictNotice] = useState<Notice>(null)
  const [predictResult, setPredictResult] = useState<ClusterPrediction | null>(null)

  const [clusterFilter, setClusterFilter] = useState('all')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const refresh = async () => {
    setLoading(true)
    try {
      const [parcelList, summary] = await Promise.all([parcelService.list(), parcelService.getClusterSummary()])
      setParcels(parcelList)
      setClusterSummary(summary)
    } catch (err) {
      setPageNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to load parcels.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleAddSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAddNotice(null)
    try {
      const payload = parcelDraftToInput(addDraft)
      setAddSubmitting(true)
      await parcelService.create(payload)
      setAddNotice({ tone: 'success', text: `Parcel ${payload.parcel_id} saved.` })
      setAddDraft(emptyParcelDraft(nextParcelId(parcels.map((p) => p.parcel_id).concat(payload.parcel_id))))
      await refresh()
    } catch (err) {
      setAddNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Failed to save parcel.' })
    } finally {
      setAddSubmitting(false)
    }
  }

  const handleCsvUpload = async () => {
    if (!csvFile) return
    setCsvUploading(true)
    setCsvNotice(null)
    try {
      const result = await parcelService.uploadCsv(csvFile)
      setCsvNotice({
        tone: result.skipped > 0 ? 'info' : 'success',
        text: `Inserted ${result.inserted} parcel${result.inserted === 1 ? '' : 's'}, skipped ${result.skipped}.`,
      })
      setCsvFile(null)
      await refresh()
    } catch (err) {
      setCsvNotice({ tone: 'error', text: err instanceof Error ? err.message : 'CSV upload failed.' })
    } finally {
      setCsvUploading(false)
    }
  }

  const handleTrain = async () => {
    setTraining(true)
    setTrainNotice(null)
    try {
      const result = await parcelService.trainClustering()
      const clusterCount = Object.keys(result.clusters).filter((key) => {
        const id = parseClusterKey(key)
        return id !== null && id >= 0
      }).length
      setTrainNotice({
        tone: 'success',
        text: `Trained on ${result.parcel_count} parcels — found ${clusterCount} cluster${clusterCount === 1 ? '' : 's'}.`,
      })
      await refresh()
    } catch (err) {
      setTrainNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Training failed.' })
    } finally {
      setTraining(false)
    }
  }

  const handlePredict = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPredictNotice(null)
    setPredictResult(null)
    try {
      const payload = parcelDraftToInput(predictDraft)
      setPredicting(true)
      const result = await parcelService.predictCluster(payload)
      setPredictResult(result)
    } catch (err) {
      setPredictNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Prediction failed.' })
    } finally {
      setPredicting(false)
    }
  }

  const toggleSelected = (parcelId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(parcelId)) next.delete(parcelId)
      else next.add(parcelId)
      return next
    })
  }

  const toggleSelectAll = (ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.length > 0 && ids.every((id) => prev.has(id))
      if (allSelected) {
        const next = new Set(prev)
        ids.forEach((id) => next.delete(id))
        return next
      }
      return new Set([...prev, ...ids])
    })
  }

  const clusterOptions = useMemo(() => {
    const ids = new Set<number>()
    parcels.forEach((p) => {
      if (p.cluster_id !== null && p.cluster_id >= 0) ids.add(p.cluster_id)
    })
    return Array.from(ids).sort((a, b) => a - b)
  }, [parcels])

  const filteredParcels = useMemo(() => {
    if (clusterFilter === 'all') return parcels
    if (clusterFilter === 'unclustered') return parcels.filter((p) => p.cluster_id === null)
    if (clusterFilter === 'noise') return parcels.filter((p) => p.cluster_id === -1)
    const id = Number(clusterFilter)
    return parcels.filter((p) => p.cluster_id === id)
  }, [parcels, clusterFilter])

  const positions = useMemo(() => normalizePositions(parcels), [parcels])

  const summaryRows = useMemo(() => {
    if (!clusterSummary) return []
    return Object.entries(clusterSummary)
      .map(([key, count]) => ({ id: parseClusterKey(key), count }))
      .sort((a, b) => (a.id === null ? -2 : a.id) - (b.id === null ? -2 : b.id))
  }, [clusterSummary])

  const totalParcels = parcels.length
  const clusteredCount = parcels.filter((p) => p.cluster_id !== null && p.cluster_id >= 0).length
  const noiseCount = parcels.filter((p) => p.cluster_id === -1).length
  const notClusteredCount = parcels.filter((p) => p.cluster_id === null).length
  const allShownSelected = filteredParcels.length > 0 && filteredParcels.every((p) => selectedIds.has(p.parcel_id))

  return (
    <div>
      <PageHeader
        action={
          <SecondaryButton onClick={refresh}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </SecondaryButton>
        }
        description="Ingest parcels, then discover natural delivery clusters with HDBSCAN density-based clustering."
        title="Parcel Consolidation"
      />

      {pageNotice && (
        <div className="mb-5">
          <InlineAlert tone={pageNotice.tone}>{pageNotice.text}</InlineAlert>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Boxes} label="Total Parcels" tone="blue" value={formatNumber(totalParcels)} />
        <MetricCard
          icon={Layers}
          label="Clustered"
          tone="green"
          trend={`${clusterOptions.length} cluster${clusterOptions.length === 1 ? '' : 's'}`}
          value={formatNumber(clusteredCount)}
        />
        <MetricCard icon={Target} label="Noise / Unassigned" tone="amber" value={formatNumber(noiseCount)} />
        <MetricCard icon={Sparkles} label="Not Clustered Yet" tone="red" value={formatNumber(notClusteredCount)} />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.6fr_0.9fr]">
        <Card title="Parcel Intake">
          {addNotice && (
            <div className="mb-4">
              <InlineAlert tone={addNotice.tone}>{addNotice.text}</InlineAlert>
            </div>
          )}
          <form className="space-y-4" onSubmit={handleAddSubmit}>
            <ParcelFieldsFieldset onChange={setAddDraft} value={addDraft} />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-fleet-line/80 pt-4">
              <span className="text-xs font-semibold text-fleet-muted">Fields mirror the backend ParcelIn schema exactly.</span>
              <PrimaryButton loading={addSubmitting} type="submit">
                <PackagePlus className="h-4 w-4" /> Add Parcel
              </PrimaryButton>
            </div>
          </form>

          <div className="mt-6 border-t border-fleet-line/80 pt-6">
            <h3 className="mb-1 text-sm font-extrabold text-fleet-ink">Bulk import via CSV</h3>
            <p className="mb-3 text-xs font-medium text-fleet-muted">Columns: {CSV_TEMPLATE_COLUMNS.join(', ')}</p>
            {csvNotice && (
              <div className="mb-3">
                <InlineAlert tone={csvNotice.tone}>{csvNotice.text}</InlineAlert>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <label className="focus-ring inline-flex cursor-pointer items-center gap-2 rounded-xl border border-fleet-line bg-white px-4 py-2.5 text-sm font-bold text-fleet-ink shadow-sm transition hover:bg-slate-50">
                <Upload className="h-4 w-4" />
                {csvFile ? csvFile.name : 'Choose CSV file'}
                <input
                  accept=".csv"
                  className="hidden"
                  onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)}
                  type="file"
                />
              </label>
              <PrimaryButton disabled={!csvFile} loading={csvUploading} onClick={handleCsvUpload}>
                Upload
              </PrimaryButton>
            </div>
          </div>
        </Card>

        <Card action={<StatusBadge tone="blue">{clusterOptions.length} clusters</StatusBadge>} title="Cluster Snapshot">
          {trainNotice && (
            <div className="mb-4">
              <InlineAlert tone={trainNotice.tone}>{trainNotice.text}</InlineAlert>
            </div>
          )}

          <div className="map-grid relative mb-4 h-48 overflow-hidden rounded-2xl border border-slate-300 shadow-inner">
            <div className="absolute inset-0 bg-slate-900/16" />
            {parcels.length === 0 ? (
              <div className="absolute inset-0 grid place-items-center text-xs font-bold text-white/80">No parcels yet</div>
            ) : (
              positions.map((pos, index) => {
                const parcel = parcels[index]
                return (
                  <span
                    className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                    key={parcel.parcel_id}
                    style={{ left: `${pos.left}%`, top: `${pos.top}%`, background: clusterColor(parcel.cluster_id) }}
                    title={`${parcel.parcel_id} · ${clusterLabel(parcel.cluster_id)}`}
                  />
                )
              })
            )}
            <div className="absolute right-3 top-3 rounded-xl bg-white/85 px-3 py-1.5 text-[11px] font-bold text-slate-600 shadow">
              Parcel geography (relative)
            </div>
          </div>

          <PrimaryButton loading={training} onClick={handleTrain}>
            <Sparkles className="h-4 w-4" /> Train HDBSCAN Model
          </PrimaryButton>

          <div className="mt-5 space-y-2.5">
            {summaryRows.length === 0 ? (
              <p className="text-xs font-medium text-fleet-muted">No cluster data yet — add parcels and train the model.</p>
            ) : (
              summaryRows.map((row) => (
                <div key={String(row.id)}>
                  <div className="mb-1 flex items-center justify-between text-sm font-bold">
                    <span className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: clusterColor(row.id) }} />
                      {clusterLabel(row.id)}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-fleet-muted">{row.count}</span>
                      {row.id !== null && row.id >= 0 && (
                        <button
                          className="text-xs font-black text-fleet-blue"
                          onClick={() => navigate('/load-optimization', { state: { clusterId: row.id } })}
                          type="button"
                        >
                          Optimize →
                        </button>
                      )}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${totalParcels ? (row.count / totalParcels) * 100 : 0}%`, background: clusterColor(row.id) }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <div className="mt-5 rounded-2xl border border-fleet-line bg-white p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <SlidersHorizontal className="h-5 w-5 text-fleet-muted" />
          <select
            className="rounded-xl border border-fleet-line px-3 py-2 text-sm font-bold"
            onChange={(event) => setClusterFilter(event.target.value)}
            value={clusterFilter}
          >
            <option value="all">All Parcels</option>
            <option value="unclustered">Not Clustered Yet</option>
            <option value="noise">Unassigned (Noise)</option>
            {clusterOptions.map((id) => (
              <option key={id} value={String(id)}>
                Cluster {id}
              </option>
            ))}
          </select>
          <button className="text-xs font-black text-fleet-blue" onClick={() => toggleSelectAll(filteredParcels.map((p) => p.parcel_id))} type="button">
            {allShownSelected ? 'Clear selection' : 'Select all shown'}
          </button>
          <span className="ml-auto text-sm font-bold text-fleet-muted">
            {filteredParcels.length} of {totalParcels} parcels shown
          </span>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3">
          <span className="text-sm font-bold text-blue-700">
            {selectedIds.size} parcel{selectedIds.size === 1 ? '' : 's'} selected
          </span>
          <div className="flex items-center gap-2">
            <SecondaryButton onClick={() => setSelectedIds(new Set())}>Clear</SecondaryButton>
            <PrimaryButton onClick={() => navigate('/load-optimization', { state: { parcelIds: Array.from(selectedIds) } })}>
              Optimize Selected Load <ArrowRight className="h-4 w-4" />
            </PrimaryButton>
          </div>
        </div>
      )}

      <div className="mt-4">
        {loading ? (
          <Card>
            <p className="text-sm font-semibold text-fleet-muted">Loading parcels…</p>
          </Card>
        ) : filteredParcels.length === 0 ? (
          <EmptyState
            description="Add a parcel above or import a CSV batch to get started."
            icon={Boxes}
            title="No parcels match this filter"
          />
        ) : (
          <DataTable headers={['', 'Parcel ID', 'Location', 'Weight', 'Volume', 'Time Window', 'Fragile', 'Cluster', 'Confidence']}>
            {filteredParcels.map((parcel) => (
              <tr className="transition hover:bg-blue-50/40" key={parcel.parcel_id}>
                <td className="px-5 py-4">
                  <input checked={selectedIds.has(parcel.parcel_id)} onChange={() => toggleSelected(parcel.parcel_id)} type="checkbox" />
                </td>
                <td className="px-5 py-4 font-black text-fleet-ink">{parcel.parcel_id}</td>
                <td className="px-5 py-4 text-fleet-muted">
                  {parcel.latitude.toFixed(4)}, {parcel.longitude.toFixed(4)}
                </td>
                <td className="px-5 py-4 font-semibold">{parcel.weight_kg} kg</td>
                <td className="px-5 py-4 font-semibold">{parcel.volume_m3} m³</td>
                <td className="px-5 py-4 text-fleet-muted">
                  {parcel.time_window_start}–{parcel.time_window_end}
                </td>
                <td className="px-5 py-4">
                  <StatusBadge tone={parcel.fragile ? 'amber' : 'slate'}>{parcel.fragile ? 'Fragile' : 'Standard'}</StatusBadge>
                </td>
                <td className="px-5 py-4">
                  <StatusBadge tone={clusterTone(parcel.cluster_id)}>{clusterLabel(parcel.cluster_id)}</StatusBadge>
                </td>
                <td className="px-5 py-4 font-semibold">
                  {parcel.cluster_probability !== null ? formatPercent(parcel.cluster_probability) : '—'}
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </div>

      <Card className="mt-5" title="Predict Cluster for a New Parcel">
        <p className="mb-4 text-sm font-medium text-fleet-muted">
          Runs HDBSCAN's approximate_predict against the last trained model — train the model above first.
        </p>
        {predictNotice && (
          <div className="mb-4">
            <InlineAlert tone={predictNotice.tone}>{predictNotice.text}</InlineAlert>
          </div>
        )}
        <form className="space-y-4" onSubmit={handlePredict}>
          <ParcelFieldsFieldset onChange={setPredictDraft} value={predictDraft} />
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-fleet-line/80 pt-4">
            {predictResult ? (
              <div className="flex items-center gap-2">
                <StatusBadge tone={predictResult.status === 'ASSIGNED' ? 'green' : 'slate'}>
                  {predictResult.status === 'ASSIGNED' ? clusterLabel(predictResult.cluster_id) : 'Unassigned (noise)'}
                </StatusBadge>
                <span className="text-xs font-bold text-fleet-muted">{formatPercent(predictResult.cluster_probability)} confidence</span>
              </div>
            ) : (
              <span />
            )}
            <PrimaryButton loading={predicting} type="submit">
              <Target className="h-4 w-4" /> Predict Cluster
            </PrimaryButton>
          </div>
        </form>
      </Card>
    </div>
  )
}
