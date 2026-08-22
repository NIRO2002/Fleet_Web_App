import { Component, useMemo, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { Edges, Grid, Html, OrbitControls } from '@react-three/drei'
import type { LoadPlanParcel, LoadPlanVehicle } from '../types'

export type CargoColorMode = 'sequence' | 'weight' | 'layer'

const PALETTE = ['#2563eb', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#dc2626', '#7c3aed']

function colorFor(parcel: LoadPlanParcel, mode: CargoColorMode, total: number) {
  if (mode === 'layer') return PALETTE[parcel.stack_layer % PALETTE.length]
  const ratio = mode === 'weight'
    ? Math.min(parcel.weight_kg / 60, 1)
    : Math.min((parcel.load_sequence - 1) / Math.max(total - 1, 1), 1)
  return `hsl(${215 - ratio * 195} 78% 52%)`
}

function compactParcelId(parcelId: string) {
  if (parcelId.length <= 14) return parcelId
  return `${parcelId.slice(0, 7)}…${parcelId.slice(-4)}`
}

function ParcelBox({ parcel, vehicle, color, onSelect, showParcelIds }: { parcel: LoadPlanParcel; vehicle: LoadPlanVehicle; color: string; onSelect: () => void; showParcelIds: boolean }) {
  const [hovered, setHovered] = useState(false)
  const length = (parcel.length_cm ?? 0) / 100
  const width = (parcel.width_cm ?? 0) / 100
  const height = (parcel.height_cm ?? 0) / 100
  const position: [number, number, number] = [
    (parcel.load_position_x + (parcel.length_cm ?? 0) / 2 - vehicle.cargo_length_cm / 2) / 100,
    (parcel.load_position_z + (parcel.height_cm ?? 0) / 2) / 100,
    (parcel.load_position_y + (parcel.width_cm ?? 0) / 2 - vehicle.cargo_width_cm / 2) / 100,
  ]
  return <group position={position}>
    <mesh
      onClick={(event) => { event.stopPropagation(); onSelect() }}
      onPointerOut={(event) => { event.stopPropagation(); setHovered(false) }}
      onPointerOver={(event) => { event.stopPropagation(); setHovered(true) }}
    >
      <boxGeometry args={[length, height, width]} />
      <meshStandardMaterial color={color} emissive={hovered ? '#ffffff' : '#000000'} emissiveIntensity={hovered ? 0.22 : 0} opacity={0.86} transparent />
      <Edges color="#0f172a" threshold={15} />
    </mesh>
    {showParcelIds && (
      <Html center distanceFactor={5} position={[0, height / 2 + 0.06, 0]} sprite transform zIndexRange={[10, 0]}>
        <div
          className="pointer-events-none select-none whitespace-nowrap rounded bg-slate-950/90 px-1.5 py-0.5 font-mono text-[10px] font-black leading-none text-white shadow-md ring-1 ring-white/50"
          title={parcel.parcel_id}
        >
          {hovered ? parcel.parcel_id : compactParcelId(parcel.parcel_id)}
        </div>
      </Html>
    )}
  </group>
}

function Scene({ vehicle, parcels, mode, onSelect, showParcelIds }: { vehicle: LoadPlanVehicle; parcels: LoadPlanParcel[]; mode: CargoColorMode; onSelect: (parcel: LoadPlanParcel) => void; showParcelIds: boolean }) {
  const bay: [number, number, number] = [vehicle.cargo_length_cm / 100, vehicle.cargo_height_cm / 100, vehicle.cargo_width_cm / 100]
  return <>
    <ambientLight intensity={1.25} />
    <directionalLight intensity={2} position={[5, 8, 5]} />
    <mesh position={[0, bay[1] / 2, 0]}>
      <boxGeometry args={bay} />
      <meshBasicMaterial color="#93c5fd" opacity={0.055} transparent />
      <Edges color="#2563eb" />
    </mesh>
    {parcels.map((parcel) => <ParcelBox color={colorFor(parcel, mode, vehicle.parcels.length)} key={parcel.parcel_id} onSelect={() => onSelect(parcel)} parcel={parcel} showParcelIds={showParcelIds} vehicle={vehicle} />)}
    <Grid args={[Math.max(bay[0], 6), Math.max(bay[0], 6)]} cellColor="#cbd5e1" cellSize={0.25} position={[0, 0, 0]} sectionColor="#94a3b8" />
    <OrbitControls makeDefault target={[0, bay[1] / 3, 0]} />
  </>
}

function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch { return false }
}

class WebGLErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('3D load view failed', error, info) }
  render() { return this.state.failed ? <Fallback /> : this.props.children }
}

function Fallback() { return <div className="grid h-[560px] place-items-center rounded-xl bg-slate-950 px-6 text-center text-sm font-semibold text-slate-200">3D view is unavailable because WebGL could not start. The load table remains available.</div> }

export function CargoBay3D({ vehicle, mode, maxLoadSequence, showParcelIds = false }: { vehicle: LoadPlanVehicle; mode: CargoColorMode; maxLoadSequence: number; showParcelIds?: boolean }) {
  const [selected, setSelected] = useState<LoadPlanParcel | null>(null)
  const visible = useMemo(() => vehicle.parcels.filter((parcel) => parcel.load_sequence <= maxLoadSequence), [vehicle.parcels, maxLoadSequence])
  if (!supportsWebGL()) return <Fallback />
  return <div className="relative h-[560px] overflow-hidden rounded-xl bg-gradient-to-b from-slate-900 to-slate-800">
    <WebGLErrorBoundary><Canvas camera={{ position: [6, 4.5, 6], fov: 45 }}><Scene mode={mode} onSelect={setSelected} parcels={visible} showParcelIds={showParcelIds} vehicle={vehicle} /></Canvas></WebGLErrorBoundary>
    <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-slate-950/75 px-3 py-2 text-xs font-semibold text-white">Door / front is at x = 0 · drag to orbit · scroll to zoom</div>
    {selected && <div className="absolute bottom-3 right-3 max-w-xs rounded-xl bg-white/95 p-4 text-sm shadow-xl"><button aria-label="Close parcel details" className="float-right font-black" onClick={() => setSelected(null)} type="button">×</button><div className="font-black">{selected.parcel_id}</div><div className="mt-1 text-slate-600">Load {selected.load_sequence} · Deliver {selected.delivery_sequence} · Layer {selected.stack_layer}</div><div className="text-slate-600">{selected.weight_kg.toFixed(1)} kg · {selected.length_cm} × {selected.width_cm} × {selected.height_cm} cm</div></div>}
  </div>
}
