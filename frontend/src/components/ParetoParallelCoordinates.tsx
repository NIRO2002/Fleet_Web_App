import { useMemo, useState } from 'react'
import { ResponsiveContainer } from 'recharts'
import type { ParetoSolution } from '../types'
import { formatNumber, formatPercent } from '../utils/format'

type Metric = 'utilization' | 'estimated_distance_km' | 'time_window_compliance' | 'fleet_cost'
const AXES: { key: Metric; label: string; format: (value: number) => string; invert?: boolean }[] = [
  { key: 'utilization', label: 'Utilization', format: (v) => formatPercent(v, 1) },
  { key: 'estimated_distance_km', label: 'Distance ↓', format: (v) => `${v.toFixed(1)} km`, invert: true },
  { key: 'time_window_compliance', label: 'TW compliance', format: (v) => formatPercent(v, 1) },
  { key: 'fleet_cost', label: 'Cost ↓', format: (v) => `LKR ${formatNumber(v)}`, invert: true },
]

export function ParetoParallelCoordinates({ solutions }: { solutions: ParetoSolution[] }) {
  const [hovered, setHovered] = useState<number | null>(null)
  const ranges = useMemo(() => Object.fromEntries(AXES.map(({ key }) => {
    const values = solutions.map((row) => row[key])
    return [key, { min: Math.min(...values), max: Math.max(...values) }]
  })) as Record<Metric, { min: number; max: number }>, [solutions])
  if (!solutions.length) return null

  return <div>
    <div className="mb-3 text-xs font-bold text-fleet-muted">Higher is better on every axis; distance and cost are inverted.</div>
    <div className="h-[360px] w-full">
      <ResponsiveContainer><ParallelSvg hovered={hovered} ranges={ranges} setHovered={setHovered} solutions={solutions} /></ResponsiveContainer>
    </div>
    {hovered !== null && <div className="rounded-xl border border-fleet-line bg-slate-50 p-3 text-sm">
      <b>{solutions[hovered].selected ? 'Selected knee point' : `Pareto solution ${hovered + 1}`}</b>
      <span className="ml-3">Util {formatPercent(solutions[hovered].utilization, 1)}</span>
      <span className="ml-3">Distance {solutions[hovered].estimated_distance_km.toFixed(1)} km</span>
      <span className="ml-3">TW {formatPercent(solutions[hovered].time_window_compliance, 1)}</span>
      <span className="ml-3">Cost LKR {formatNumber(solutions[hovered].fleet_cost)}</span>
      <span className="ml-3">{solutions[hovered].n_vehicles} vehicles</span>
      <span className="ml-3">LKR {formatNumber(solutions[hovered].cost_per_parcel)} / parcel</span>
    </div>}
  </div>
}

function ParallelSvg({ width = 800, height = 360, solutions, ranges, hovered, setHovered }: {
  width?: number; height?: number; solutions: ParetoSolution[];
  ranges: Record<Metric, { min: number; max: number }>; hovered: number | null;
  setHovered: (index: number | null) => void
}) {
  const w = Number(width), h = Number(height)
  const left = 92, right = 92, top = 28, bottom = 58
  const chartWidth = Math.max(1, w - left - right), chartHeight = Math.max(1, h - top - bottom)
  const x = (index: number) => left + chartWidth * index / (AXES.length - 1)
  const normalized = (solution: ParetoSolution, key: Metric, invert?: boolean) => {
    const range = ranges[key]
    const raw = range.max - range.min > 1e-12 ? (solution[key] - range.min) / (range.max - range.min) : 1
    return invert ? 1 - raw : raw
  }
  const y = (value: number) => top + (1 - value) * chartHeight
  return <svg height={h} role="img" viewBox={`0 0 ${w} ${h}`} width={w}>
    {AXES.map((axis, axisIndex) => <g key={axis.key}>
      <line stroke="#94a3b8" x1={x(axisIndex)} x2={x(axisIndex)} y1={top} y2={top + chartHeight}/>
      <text fill="#334155" fontSize="12" fontWeight="700" textAnchor="middle" x={x(axisIndex)} y={h - 18}>{axis.label}</text>
      {[0, .5, 1].map((tick) => {
        const range = ranges[axis.key], raw = axis.invert ? 1 - tick : tick
        const real = range.min + raw * (range.max - range.min)
        const anchor = axisIndex === 0 ? 'end' : axisIndex === AXES.length - 1 ? 'start' : 'middle'
        const offset = axisIndex === 0 ? -7 : axisIndex === AXES.length - 1 ? 7 : 0
        return <g key={tick}><line stroke="#cbd5e1" x1={x(axisIndex) - 4} x2={x(axisIndex) + 4} y1={y(tick)} y2={y(tick)}/><text fill="#64748b" fontSize="10" textAnchor={anchor} x={x(axisIndex) + offset} y={y(tick) - 5}>{axis.format(real)}</text></g>
      })}
    </g>)}
    {solutions.map((solution, index) => {
      const active = hovered === index
      const points = AXES.map((axis, axisIndex) => `${x(axisIndex)},${y(normalized(solution, axis.key, axis.invert))}`).join(' ')
      return <polyline fill="none" key={index} onMouseEnter={() => setHovered(index)} onMouseLeave={() => setHovered(null)} points={points} stroke={solution.selected ? '#dc2626' : active ? '#2563eb' : '#94a3b8'} strokeOpacity={solution.selected || active ? 1 : .28} strokeWidth={solution.selected ? 4 : active ? 3 : 1.25}/>
    })}
  </svg>
}
