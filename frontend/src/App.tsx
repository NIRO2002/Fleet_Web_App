import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthPage } from './components/AuthLayout'
import { AppShell } from './components/Shell'
import { authService } from './services/authService'
import { LoadOptimizationPage } from './pages/LoadOptimizationPage'
import { ParcelConsolidationPage } from './pages/ParcelConsolidationPage'
import { VehicleTypesPage } from './pages/VehicleTypesPage'
import { LoadPlanPage } from './pages/LoadPlanPage'
import { LoadedVehiclesPage } from './pages/LoadedVehiclesPage'

function RequireAuth() {
  return authService.getSession() ? <AppShell /> : <Navigate replace to="/login" />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AuthPage mode="login" />} path="/login" />
        <Route element={<AuthPage mode="register" />} path="/register" />
        <Route element={<RequireAuth />}>
          <Route element={<Navigate replace to="/parcel-consolidation" />} index />
          <Route element={<ParcelConsolidationPage />} path="/parcel-consolidation" />
          <Route element={<LoadOptimizationPage />} path="/load-optimization" />
          <Route element={<LoadPlanPage />} path="/load-plans/:planId?" />
          <Route element={<LoadedVehiclesPage />} path="/loaded-vehicles" />
          <Route element={<VehicleTypesPage />} path="/vehicle-types" />
        </Route>
        <Route element={<Navigate replace to="/parcel-consolidation" />} path="*" />
      </Routes>
    </BrowserRouter>
  )
}

export default App
