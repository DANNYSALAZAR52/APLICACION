import { Suspense, lazy } from 'react'
import { Link, Route, Routes } from 'react-router-dom'

import type { ApiClient } from '../api/client'
import { LoadingState } from '../components/common'
import { AuditPage } from '../features/audit/AuditPage'
import { AuthProvider } from '../features/auth/AuthProvider'
import { HomeRedirect } from '../features/auth/HomeRedirect'
import { LoginPage } from '../features/auth/LoginPage'
import { PendingPage } from '../features/auth/PendingPage'
import { RequireAuth, RequirePermission } from '../features/auth/RequirePermission'
import { DriverPage } from '../features/driver/DriverPage'
import { IndicatorsPage } from '../features/indicators/IndicatorsPage'
import { MastersPage } from '../features/masters/MastersPage'
import { PatternsPage } from '../features/patterns/PatternsPage'
import { RoutingLayout } from '../features/routing/RoutingLayout'
import { TenantAdminPage } from '../features/tenant-admin/TenantAdminPage'
import { Shell } from './Shell'

// Las pantallas de ruteo arrastran el mapa (Leaflet): se cargan solo cuando se necesitan.
const TowerPage = lazy(() =>
  import('../features/routing/TowerPage').then((m) => ({ default: m.TowerPage })),
)
const TimelinePage = lazy(() =>
  import('../features/routing/TimelinePage').then((m) => ({ default: m.TimelinePage })),
)
const EventsPage = lazy(() =>
  import('../features/routing/EventsPage').then((m) => ({ default: m.EventsPage })),
)

// La pantalla de capacidad arrastra la biblioteca de gráficos: se carga solo cuando se necesita.
const CapacityPage = lazy(() =>
  import('../features/capacity/CapacityPage').then((m) => ({ default: m.CapacityPage })),
)

function NotFound() {
  return (
    <div className="alert alert-error" role="alert">
      <strong>Página no encontrada</strong>
      <p>
        <Link to="/">Volver al inicio</Link>
      </p>
    </div>
  )
}

/** Rutas y proveedores. El enrutador (BrowserRouter / MemoryRouter) lo aporta quien monta la app. */
export function App({ client }: { client: ApiClient }) {
  return (
    <AuthProvider client={client}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <Shell />
            </RequireAuth>
          }
        >
          <Route index element={<HomeRedirect />} />
          <Route
            path="/capacidad"
            element={
              <RequirePermission permission="capacity:read">
                <Suspense fallback={<LoadingState label="Cargando pantalla…" />}>
                  <CapacityPage />
                </Suspense>
              </RequirePermission>
            }
          />
          <Route
            element={
              <RequirePermission permission="routing:read">
                <RoutingLayout />
              </RequirePermission>
            }
          >
            <Route
              path="/torre-de-control"
              element={
                <Suspense fallback={<LoadingState label="Cargando mapa…" />}>
                  <TowerPage />
                </Suspense>
              }
            />
            <Route
              path="/linea-de-tiempo"
              element={
                <Suspense fallback={<LoadingState label="Cargando pantalla…" />}>
                  <TimelinePage />
                </Suspense>
              }
            />
            <Route
              path="/eventos"
              element={
                <RequirePermission permission="routing:events">
                  <Suspense fallback={<LoadingState label="Cargando pantalla…" />}>
                    <EventsPage />
                  </Suspense>
                </RequirePermission>
              }
            />
          </Route>
          <Route
            path="/mi-ruta"
            element={
              <RequirePermission permission="driver:route">
                <DriverPage />
              </RequirePermission>
            }
          />
          <Route
            path="/maestros"
            element={
              <RequirePermission permission="master_data:manage">
                <MastersPage />
              </RequirePermission>
            }
          />
          <Route
            path="/indicadores"
            element={
              <RequirePermission permission="indicators:read">
                <IndicatorsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/patrones"
            element={
              <RequirePermission permission="patterns:read">
                <PatternsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/empresas"
            element={
              <RequirePermission permission="tenants:manage">
                <TenantAdminPage />
              </RequirePermission>
            }
          />
          <Route
            path="/auditoria"
            element={
              <RequirePermission permission="audit:read">
                <AuditPage />
              </RequirePermission>
            }
          />
          <Route path="/proximamente" element={<PendingPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
