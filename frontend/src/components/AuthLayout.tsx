import { Boxes, Eye, EyeOff, Lock, Mail, Route, ShieldCheck, Sparkles, UserPlus } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authService } from '../services/authService'
import type { UserRole } from '../types'

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const [showPassword, setShowPassword] = useState(false)
  const [role, setRole] = useState<UserRole>('planner')
  const [remember, setRemember] = useState(true)
  const navigate = useNavigate()

  const isRegister = mode === 'register'

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const email = String(data.get('email') || 'planner@fleetopt.ai')
    const password = String(data.get('password') || 'fleetopt')
    const organization = String(data.get('organization') || 'FleetOpt AI Research Lab')
    if (isRegister) {
      await authService.register({
        email,
        password,
        organization,
        role,
        name: String(data.get('name') || 'Operations Planner'),
      })
    } else {
      await authService.login({ email, password, organization, role })
    }
    navigate('/parcel-consolidation')
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#dbeafe,transparent_32%),linear-gradient(135deg,#eef4ff,#f8fafc_45%,#ffffff)] p-4 text-fleet-ink">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-6xl overflow-hidden rounded-[28px] border border-white/80 bg-white/68 shadow-2xl backdrop-blur-xl lg:grid-cols-[1.05fr_0.95fr]">
        <section className="relative hidden overflow-hidden bg-gradient-to-br from-[#11327d] via-[#1d4ed8] to-[#0f766e] p-10 text-white lg:block">
          <div className="absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/12 blur-2xl" />
          <div className="absolute bottom-10 left-10 right-10 h-56 rounded-[32px] border border-white/15 bg-white/10 backdrop-blur">
            <div className="map-grid absolute inset-4 rounded-3xl opacity-60" />
            <div className="absolute bottom-6 left-6 rounded-2xl bg-white/88 p-4 text-fleet-ink shadow-xl">
              <div className="text-xs font-black uppercase tracking-wide text-blue-700">Feasible virtual loads</div>
              <div className="mt-2 flex items-end gap-3">
                <span className="text-4xl font-black">4</span>
                <span className="pb-1 text-sm font-bold text-emerald-600">of 4 vehicle types</span>
              </div>
            </div>
          </div>
          <div className="relative z-10">
            <div className="mb-12 flex items-center gap-3">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-white text-fleet-blue">
                <Boxes className="h-6 w-6" />
              </div>
              <div>
                <div className="text-2xl font-black">FleetOpt AI</div>
                <div className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-100">Parcel &amp; Load Optimization</div>
              </div>
            </div>
            <h1 className="max-w-xl text-5xl font-black leading-[1.04] tracking-tight">
              Cluster parcels and pick the right virtual vehicle in one workspace.
            </h1>
            <p className="mt-6 max-w-lg text-base font-medium leading-7 text-blue-50/90">
              Frontend for the HDBSCAN parcel-consolidation and NSGA-II load-optimization research pipeline.
              Real fleet assignment is intentionally out of scope for this module.
            </p>
            <div className="mt-8 grid max-w-lg grid-cols-2 gap-3">
              {['HDBSCAN Clustering', 'NSGA-II Load Selection', 'Virtual Vehicle Loads', 'Dynamic Insertion'].map((item) => (
                <div className="rounded-2xl bg-white/12 p-4 text-sm font-bold ring-1 ring-white/12" key={item}>
                  {item}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="flex items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-md">
            <div className="mb-8 text-center lg:text-left">
              <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-blue-50 text-fleet-blue lg:mx-0">
                {isRegister ? <UserPlus className="h-6 w-6" /> : <ShieldCheck className="h-6 w-6" />}
              </div>
              <h2 className="text-3xl font-black tracking-tight">{isRegister ? 'Create planner account' : 'System access'}</h2>
              <p className="mt-2 text-sm font-medium text-fleet-muted">
                {isRegister ? 'Register a planner account for the optimization workspace.' : 'Use any email and password for the local frontend demo.'}
              </p>
            </div>

            <form className="space-y-4" onSubmit={submit}>
              {isRegister && <Field name="name" label="Full name" placeholder="Nirasha Perera" />}
              <Field icon={Mail} name="email" label="Email address" placeholder="planner@fleetopt.ai" type="email" />
              <div>
                <label className="mb-2 block text-sm font-extrabold text-fleet-ink" htmlFor="password">
                  Password
                </label>
                <div className="flex items-center rounded-2xl border border-fleet-line bg-white px-3 shadow-sm focus-within:ring-4 focus-within:ring-blue-100">
                  <Lock className="h-4 w-4 text-fleet-muted" />
                  <input
                    className="min-h-12 flex-1 bg-transparent px-3 text-sm font-semibold outline-none"
                    defaultValue="fleetopt2026"
                    id="password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                  />
                  <button className="text-fleet-muted" onClick={() => setShowPassword((value) => !value)} type="button">
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full w-4/5 rounded-full bg-gradient-to-r from-fleet-amber to-fleet-green" />
                </div>
              </div>

              <Field name="organization" label="Organization / invite code" placeholder="FleetOpt AI Research Lab" />

              <div>
                <label className="mb-2 block text-sm font-extrabold text-fleet-ink" htmlFor="role">
                  Authorized role
                </label>
                <select
                  className="min-h-12 w-full rounded-2xl border border-fleet-line bg-white px-3 text-sm font-bold text-fleet-ink shadow-sm outline-none focus:ring-4 focus:ring-blue-100"
                  id="role"
                  onChange={(event) => setRole(event.target.value as UserRole)}
                  value={role}
                >
                  <option value="planner">Planner</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center gap-2 font-semibold text-fleet-muted">
                  <input checked={remember} onChange={(event) => setRemember(event.target.checked)} type="checkbox" />
                  Remember this device
                </label>
                <a className="font-extrabold text-fleet-blue" href="#help">
                  Help
                </a>
              </div>

              <button className="focus-ring flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-fleet-blue px-5 text-sm font-black text-white shadow-soft transition hover:-translate-y-0.5 hover:bg-blue-700" type="submit">
                <Sparkles className="h-4 w-4" />
                {isRegister ? 'Create account' : 'Login'}
              </button>
            </form>

            <div className="mt-6 rounded-2xl border border-fleet-line bg-slate-50 p-4 text-center text-sm font-semibold text-fleet-muted">
              {isRegister ? 'Already have access?' : 'Need an account?'}{' '}
              <Link className="font-black text-fleet-blue" to={isRegister ? '/login' : '/register'}>
                {isRegister ? 'Go to login' : 'Register'}
              </Link>
            </div>

            <div className="mt-4 flex items-center justify-center gap-1.5 text-xs font-semibold text-fleet-muted">
              <Route className="h-3.5 w-3.5" />
              Parcel ingestion → HDBSCAN clustering → NSGA-II load optimization
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}

function Field({
  name,
  label,
  placeholder,
  type = 'text',
  icon: Icon,
}: {
  name: string
  label: string
  placeholder: string
  type?: string
  icon?: typeof Mail
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-extrabold text-fleet-ink" htmlFor={name}>
        {label}
      </label>
      <div className="flex items-center rounded-2xl border border-fleet-line bg-white px-3 shadow-sm focus-within:ring-4 focus-within:ring-blue-100">
        {Icon && <Icon className="h-4 w-4 text-fleet-muted" />}
        <input
          className="min-h-12 flex-1 bg-transparent px-3 text-sm font-semibold outline-none"
          id={name}
          name={name}
          placeholder={placeholder}
          type={type}
        />
      </div>
    </div>
  )
}
