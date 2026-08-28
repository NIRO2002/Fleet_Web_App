import { Component, useMemo, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { Edges, Grid, Html, OrbitControls } from '@react-three/drei'
import type { LoadPlanParcel, LoadPlanVehicle } from '../types'

export type CargoColorMode = 'sequence' | 'weight' | 'layer' | 'fragility'

const PALETTE = ['#2563eb', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#dc2626', '#7c3aed']
const FRAGILE_COLOR = '#dc2626'
const FRAGILE_EDGE_COLOR = '#ef4444'
const NEUTRAL_COLOR = '#64748b'

function colorFor(parcel: LoadPlanParcel, mode: CargoColorMode, total: number) {
  if (mode === 'fragility') return parcel.fragile ? FRAGILE_COLOR : NEUTRAL_COLOR
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
  const fragile = parcel.fragile
  const length = (parcel.length_cm ?? 0) / 100
  const width = (parcel.width_cm ?? 0) / 100
  const height = (parcel.height_cm ?? 0) / 100
  const position: [number, number, number] = [
    (parcel.load_position_x + (parcel.length_cm ?? 0) / 2 - vehicle.cargo_length_cm / 2) / 100,
    (parcel.load_position_z + (parcel.height_cm ?? 0) / 2) / 100,
    (parcel.load_position_y + (parcel.width_cm ?? 0) / 2 - vehicle.cargo_width_cm / 2) / 100,
  ]
  // Fragile parcels always get a red outline + badge, on top of whatever
  // fill color the active "Color by" mode assigns -- so switching modes
  // never hides which parcels are fragile, and the dedicated "fragility"
  // mode's full red fill (see colorFor) isn't the only place it shows up.
  const badgeLabel = fragile
    ? `⚠ Fragile${showParcelIds ? ` · ${hovered ? parcel.parcel_id : compactParcelId(parcel.parcel_id)}` : ''}`
    : hovered ? parcel.parcel_id : compactParcelId(parcel.parcel_id)
  return <group position={position}>
    <mesh
      onClick={(event) => { event.stopPropagation(); onSelect() }}
      onPointerOut={(event) => { event.stopPropagation(); setHovered(false) }}
      onPointerOver={(event) => { event.stopPropagation(); setHovered(true) }}
    >
      <boxGeometry args={[length, height, width]} />
      <meshStandardMaterial
        color={color}
        emissive={hovered ? '#ffffff' : fragile ? '#7f1d1d' : '#000000'}
        emissiveIntensity={hovered ? 0.22 : fragile ? 0.16 : 0}
        opacity={0.86}
        transparent
      />
      <Edges color={fragile ? FRAGILE_EDGE_COLOR : '#0f172a'} lineWidth={fragile ? 2.5 : 1} threshold={15} />
    </mesh>
    {(showParcelIds || fragile) && (
      <Html center distanceFactor={5} position={[0, height / 2 + 0.06, 0]} sprite transform zIndexRange={[10, 0]}>
        <div
          className={`pointer-events-none select-none whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[10px] font-black leading-none shadow-md ring-1 ${fragile ? 'bg-red-600/95 text-white ring-red-200' : 'bg-slate-950/90 text-white ring-white/50'}`}
          title={fragile ? `${parcel.parcel_id} (fragile)` : parcel.parcel_id}
        >
          {badgeLabel}
        </div>
      </Html>
    )}
  </group>
}

/** Small pill label + a cone pointer anchored just outside one face of the
 * cargo bay, oriented so the cone always points back toward the bay
 * regardless of camera orbit (unlike a flat HTML glyph, real 3D geometry
 * stays correct from any angle). */
function DirectionMarker({ position, label, coneRotation }: { position: [number, number, number]; label: string; coneRotation: [number, number, number] }) {
  return <group position={position}>
    <mesh rotation={coneRotation}>
      <coneGeometry args={[0.09, 0.24, 12]} />
      <meshStandardMaterial color="#0f172a" />
    </mesh>
    <Html center distanceFactor={8} position={[0, 0.26, 0]} sprite zIndexRange={[30, 0]}>
      <div className="pointer-events-none select-none whitespace-nowrap rounded-full bg-slate-950/90 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-white shadow-lg ring-1 ring-white/40">
        {label}
      </div>
    </Html>
  </group>
}

/** Front/Back/Left/Right markers anchored to the cargo bay's own bounding
 * box, so they scale and reposition correctly for any vehicle size.
 *
 * Coordinate convention -- per the authoritative definition in
 * app/optimization/placement.py's own docstring: "x (load_position_x) is
 * measured from the cargo doors (x=0) toward the front/deepest wall
 * (x=cargo_length_cm)". Doors and "front" are opposite ends, not the same
 * point -- for a delivery truck the cargo doors are at the *rear*, and the
 * deepest wall (nearest the cab) is the actual front. (An earlier version
 * of this component's on-screen hint conflated the two as "door / front is
 * at x=0", which put these labels backwards -- fixed here.) ParcelBox
 * centers the bay on the three.js X axis, so x=0 (doors/back) lands at the
 * bay's -X extreme and x=cargo_length_cm (front) at +X. Cargo width maps
 * to the three.js Z axis.
 *
 * Left/Right are defined relative to the vehicle, not the screen/camera
 * (the view can be freely orbited): the standard convention for a
 * vehicle's own left/right (driver's-side/passenger's-side, same idea as
 * port/starboard on a ship) is the driver's perspective facing the
 * direction of travel -- forward, toward the front (+X, see above), with
 * up = +Y. By the right-hand "right = forward × up" rule:
 * right = (+X) × (+Y) = +Z. So Right is placed at the +Z side and Left at
 * the -Z side. */
function DirectionMarkers({ bay }: { bay: [number, number, number] }) {
  const marginX = Math.max(0.5, bay[0] * 0.12)
  const marginZ = Math.max(0.5, bay[2] * 0.12)
  const y = bay[1] / 2
  const halfPi = Math.PI / 2
  return <>
    <DirectionMarker coneRotation={[0, 0, halfPi]} label="Front" position={[bay[0] / 2 + marginX, y, 0]} />
    <DirectionMarker coneRotation={[0, 0, -halfPi]} label="Back" position={[-bay[0] / 2 - marginX, y, 0]} />
    <DirectionMarker coneRotation={[halfPi, 0, 0]} label="Left" position={[0, y, -bay[2] / 2 - marginZ]} />
    <DirectionMarker coneRotation={[-halfPi, 0, 0]} label="Right" position={[0, y, bay[2] / 2 + marginZ]} />
  </>
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
    <DirectionMarkers bay={bay} />
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
  const fragileVisibleCount = useMemo(() => visible.filter((parcel) => parcel.fragile).length, [visible])
  if (!supportsWebGL()) return <Fallback />
  return <div className="relative h-[560px] overflow-hidden rounded-xl bg-gradient-to-b from-slate-900 to-slate-800">
    <WebGLErrorBoundary><Canvas camera={{ position: [6, 4.5, 6], fov: 45 }}><Scene mode={mode} onSelect={setSelected} parcels={visible} showParcelIds={showParcelIds} vehicle={vehicle} /></Canvas></WebGLErrorBoundary>
    <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-slate-950/75 px-3 py-2 text-xs font-semibold text-white">Cargo doors are at x = 0 (Back) · front/deepest wall is x = cargo length (Front) · Left/Right as if facing forward from the driver's seat · drag to orbit · scroll to zoom</div>
    {fragileVisibleCount > 0 && (
      <div className="pointer-events-none absolute right-3 top-3 flex items-center gap-1.5 rounded-lg bg-red-600/90 px-3 py-2 text-xs font-black text-white shadow-lg">
        <span aria-hidden>⚠</span> {fragileVisibleCount} fragile parcel{fragileVisibleCount === 1 ? '' : 's'}
      </div>
    )}
    {selected && <div className="absolute bottom-3 right-3 max-w-xs rounded-xl bg-white/95 p-4 text-sm shadow-xl"><button aria-label="Close parcel details" className="float-right font-black" onClick={() => setSelected(null)} type="button">×</button><div className="font-black">{selected.parcel_id}{selected.fragile && <span className="ml-2 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-black uppercase text-white">Fragile</span>}</div><div className="mt-1 text-slate-600">Load {selected.load_sequence} · Deliver {selected.delivery_sequence} · Layer {selected.stack_layer}</div><div className="text-slate-600">{selected.weight_kg.toFixed(1)} kg · {selected.length_cm} × {selected.width_cm} × {selected.height_cm} cm</div></div>}
  </div>
}
