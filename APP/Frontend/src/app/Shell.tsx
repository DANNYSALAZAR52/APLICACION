import { NavLink, Outlet } from 'react-router-dom'

import type { Permission } from '../api/types'
import { DemoBanner } from '../components/common'
import { can, roleLabel } from '../domain-ui/roles'
import { useAuth } from '../features/auth/AuthProvider'

interface NavItem {
  to: string
  label: string
  permission: Permission
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/mi-ruta', label: 'Mi hoja de ruta', permission: 'driver:route' },
  { to: '/torre-de-control', label: 'Torre de control', permission: 'routing:read' },
  { to: '/linea-de-tiempo', label: 'Línea de tiempo', permission: 'routing:read' },
  { to: '/eventos', label: 'Eventos y re-ruteo', permission: 'routing:events' },
  { to: '/capacidad', label: 'Capacidad de flota', permission: 'capacity:read' },
  { to: '/indicadores', label: 'Indicadores diarios', permission: 'indicators:read' },
  { to: '/patrones', label: 'Patrones detectados', permission: 'patterns:read' },
  { to: '/maestros', label: 'Maestros y parámetros', permission: 'master_data:manage' },
  { to: '/empresas', label: 'Administración de empresas', permission: 'tenants:manage' },
  { to: '/auditoria', label: 'Auditoría', permission: 'audit:read' },
]

// Pantallas planificadas que todavía no existen: se muestran deshabilitadas y explicadas.
export const PENDING_ITEMS: { label: string; permission: Permission }[] = []

export function Shell() {
  const { user, logout } = useAuth()
  if (!user) return null
  const permissions = user.permissions
  const enabled = NAV_ITEMS.filter((item) => can(permissions, item.permission))
  const pending = PENDING_ITEMS.filter((item) => can(permissions, item.permission))

  return (
    <div className="shell">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <DemoBanner />
      <header className="topbar">
        <div className="brand">Planeación de flota</div>
        <div className="userbox">
          <div>
            <strong>{user.display_name}</strong>
            <div className="muted small">
              {roleLabel(user.role)} · {user.tenant_name ?? 'Sin empresa (global)'}
            </div>
          </div>
          <button type="button" className="btn" onClick={() => void logout()}>
            Cerrar sesión
          </button>
        </div>
      </header>
      <div className="layout">
        <nav className="sidenav" aria-label="Navegación principal">
          <ul>
            {enabled.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to}>{item.label}</NavLink>
              </li>
            ))}
          </ul>
          {pending.length > 0 ? (
            <>
              <p className="nav-heading">Próximamente</p>
              <ul>
                {pending.map((item) => (
                  <li key={item.label}>
                    <span
                      className="nav-disabled"
                      aria-disabled="true"
                      title="Esta pantalla estará disponible en una fase posterior del demo"
                    >
                      {item.label}
                      <span className="visually-hidden">
                        {' '}
                        (no disponible: se construye en una fase posterior)
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </nav>
        <main id="contenido" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
