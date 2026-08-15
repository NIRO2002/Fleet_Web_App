import type { ReactNode } from 'react'
import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Info, Loader2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ParcelDraft, VehicleCapabilityDraft } from '../types'

export function Card({
  title,
  action,
  children,
  className,
}: {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={clsx('rounded-2xl border border-fleet-line bg-white shadow-card', className)}>
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-fleet-line/80 px-5 py-4">
          {title && <h2 className="text-base font-extrabold text-fleet-ink">{title}</h2>}
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function MetricCard({
  label,
  value,
  trend,
  icon: Icon,
  tone = 'blue',
}: {
  label: string
  value: string
  trend?: string
  icon: LucideIcon
  tone?: 'blue' | 'green' | 'amber' | 'red'
}) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    red: 'bg-red-50 text-red-700',
  }
  return (
    <div className="rounded-2xl border border-fleet-line bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-soft">
      <div className="mb-5 flex items-center justify-between">
        <span className="text-sm font-bold text-fleet-muted">{label}</span>
        <span className={clsx('grid h-10 w-10 place-items-center rounded-xl', tones[tone])}>
          <Icon className="h-5 w-5" />
        </span>
      </div>
      <div className="flex items-end gap-3">
        <div className="text-3xl font-black tracking-tight">{value}</div>
        {trend && (
          <div className={clsx('mb-1 rounded-md px-2 py-1 text-xs font-bold', tone === 'red' ? 'bg-red-50 text-red-700' : 'bg-blue-50 text-blue-700')}>
            {trend}
          </div>
        )}
      </div>
    </div>
  )
}

export function StatusBadge({ children, tone = 'blue' }: { children: ReactNode; tone?: 'blue' | 'green' | 'amber' | 'red' | 'slate' }) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 ring-blue-200',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    amber: 'bg-amber-50 text-amber-700 ring-amber-200',
    red: 'bg-red-50 text-red-700 ring-red-200',
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
  }
  return <span className={clsx('inline-flex items-center rounded-md px-2 py-1 text-xs font-bold ring-1', tones[tone])}>{children}</span>
}

export function PrimaryButton({
  children,
  onClick,
  type = 'button',
  disabled = false,
  loading = false,
}: {
  children: ReactNode
  onClick?: () => void
  type?: 'button' | 'submit'
  disabled?: boolean
  loading?: boolean
}) {
  return (
    <button
      className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl bg-fleet-blue px-4 py-2.5 text-sm font-extrabold text-white shadow-soft transition hover:-translate-y-0.5 hover:bg-blue-700 disabled:pointer-events-none disabled:opacity-60"
      disabled={disabled || loading}
      onClick={onClick}
      type={type}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

export function SecondaryButton({
  children,
  onClick,
  disabled = false,
  type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  type?: 'button' | 'submit'
}) {
  return (
    <button
      className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl border border-fleet-line bg-white px-4 py-2.5 text-sm font-bold text-fleet-ink shadow-sm transition hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-60"
      disabled={disabled}
      onClick={onClick}
      type={type}
    >
      {children}
    </button>
  )
}

export function PageHeader({
  title,
  description,
  action,
  eyebrow,
}: {
  title: string
  description: string
  action?: ReactNode
  eyebrow?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div>
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <h2 className="text-3xl font-black tracking-tight text-fleet-ink">{title}</h2>
        <p className="mt-1 text-sm font-medium text-fleet-muted">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function DataTable({
  headers,
  children,
}: {
  headers: string[]
  children: ReactNode
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-fleet-line bg-white shadow-card">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-100 text-xs font-black uppercase tracking-wide text-slate-500">
            <tr>
              {headers.map((header) => (
                <th className="px-5 py-3" key={header}>
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-fleet-line">{children}</tbody>
        </table>
      </div>
    </div>
  )
}

export function InlineAlert({ tone = 'info', children }: { tone?: 'info' | 'success' | 'error'; children: ReactNode }) {
  const tones = {
    info: 'border-blue-200 bg-blue-50 text-blue-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    error: 'border-red-200 bg-red-50 text-red-700',
  }
  const Icon = tone === 'error' ? AlertTriangle : tone === 'success' ? CheckCircle2 : Info
  return (
    <div className={clsx('flex items-start gap-2 rounded-xl border px-4 py-3 text-sm font-semibold', tones[tone])}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  )
}

export function CapacityBar({ label, used, capacity, unit }: { label: string; used: number; capacity: number; unit: string }) {
  const pct = capacity > 0 ? Math.min(100, (used / capacity) * 100) : 0
  const tone = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs font-bold text-fleet-muted">
        <span>{label}</span>
        <span>
          {used.toFixed(1)}
          {unit} / {capacity.toFixed(1)}
          {unit}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={clsx('h-full rounded-full transition-all', tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-fleet-line bg-slate-50/60 px-6 py-10 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-xl bg-blue-50 text-fleet-blue">
        <Icon className="h-5 w-5" />
      </span>
      <div className="text-sm font-extrabold text-fleet-ink">{title}</div>
      <p className="max-w-sm text-xs font-medium text-fleet-muted">{description}</p>
      {action}
    </div>
  )
}

export function LabeledInput({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  step,
  readOnly = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
  step?: string
  readOnly?: boolean
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-fleet-muted">{label}</span>
      <input
        className="focus-ring min-h-11 w-full rounded-xl border border-fleet-line bg-white px-3 text-sm font-semibold text-fleet-ink shadow-sm outline-none focus:ring-4 focus:ring-blue-100 disabled:bg-slate-50"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        step={step}
        type={type}
        value={value}
      />
    </label>
  )
}

export function LabeledSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-fleet-muted">{label}</span>
      <select
        className="focus-ring min-h-11 w-full rounded-xl border border-fleet-line bg-white px-3 text-sm font-semibold text-fleet-ink shadow-sm outline-none focus:ring-4 focus:ring-blue-100"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

/** Shared field grid for capturing a VehicleCapabilityInput via a VehicleCapabilityDraft
 * (used for the vehicle type intake + edit forms). */
export function VehicleCapabilityFieldsFieldset({
  value,
  onChange,
}: {
  value: VehicleCapabilityDraft
  onChange: (next: VehicleCapabilityDraft) => void
}) {
  const set = <K extends keyof VehicleCapabilityDraft>(key: K, next: VehicleCapabilityDraft[K]) => onChange({ ...value, [key]: next })

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <LabeledInput label="Vehicle Name" onChange={(v) => set('name', v)} placeholder="Bajaj Three Wheeler" value={value.name} />
      <LabeledInput label="Category" onChange={(v) => set('category', v)} placeholder="Three Wheeler" value={value.category} />
      <LabeledInput label="Brand" onChange={(v) => set('brand', v)} placeholder="Bajaj" value={value.brand} />
      <LabeledInput label="Model" onChange={(v) => set('model', v)} placeholder="RE" value={value.model} />
      <LabeledInput
        label="Maximum Weight (kg)"
        onChange={(v) => set('max_weight_kg', v)}
        placeholder="500"
        step="0.1"
        type="number"
        value={value.max_weight_kg}
      />
      <LabeledSelect
        label="Status"
        onChange={(v) => set('status', v as VehicleCapabilityDraft['status'])}
        options={[
          { value: 'ACTIVE', label: 'Active' },
          { value: 'INACTIVE', label: 'Inactive' },
        ]}
        value={value.status}
      />
      <LabeledInput
        label="Maximum Length (cm)"
        onChange={(v) => set('max_length_cm', v)}
        placeholder="180"
        step="0.1"
        type="number"
        value={value.max_length_cm}
      />
      <LabeledInput
        label="Maximum Width (cm)"
        onChange={(v) => set('max_width_cm', v)}
        placeholder="140"
        step="0.1"
        type="number"
        value={value.max_width_cm}
      />
      <LabeledInput
        label="Maximum Height (cm)"
        onChange={(v) => set('max_height_cm', v)}
        placeholder="130"
        step="0.1"
        type="number"
        value={value.max_height_cm}
      />
    </div>
  )
}

/** Shared field grid for capturing a ParcelInput via a ParcelDraft (used for intake + insertion forms). */
export function ParcelFieldsFieldset({
  value,
  onChange,
  idReadOnly = false,
}: {
  value: ParcelDraft
  onChange: (next: ParcelDraft) => void
  idReadOnly?: boolean
}) {
  const set = <K extends keyof ParcelDraft>(key: K, next: ParcelDraft[K]) => onChange({ ...value, [key]: next })

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <LabeledInput
        label="Parcel ID"
        onChange={(v) => set('parcel_id', v)}
        placeholder="P006"
        readOnly={idReadOnly}
        value={value.parcel_id}
      />
      <label className="flex items-end pb-2.5">
        <span className="flex items-center gap-2 text-sm font-bold text-fleet-ink">
          <input checked={value.fragile} onChange={(event) => set('fragile', event.target.checked)} type="checkbox" />
          Fragile item
        </span>
      </label>
      <LabeledInput label="Latitude" onChange={(v) => set('latitude', v)} placeholder="6.9271" step="0.0001" type="number" value={value.latitude} />
      <LabeledInput label="Longitude" onChange={(v) => set('longitude', v)} placeholder="79.8612" step="0.0001" type="number" value={value.longitude} />
      <LabeledInput label="Weight (kg)" onChange={(v) => set('weight_kg', v)} placeholder="2.5" step="0.1" type="number" value={value.weight_kg} />
      <LabeledInput label="Volume (m³)" onChange={(v) => set('volume_m3', v)} placeholder="0.015" step="0.001" type="number" value={value.volume_m3} />
      <LabeledInput label="Time Window Start" onChange={(v) => set('time_window_start', v)} type="time" value={value.time_window_start} />
      <LabeledInput label="Time Window End" onChange={(v) => set('time_window_end', v)} type="time" value={value.time_window_end} />
    </div>
  )
}
