import type { ReactNode } from 'react'
import { Link, Navigate } from 'react-router-dom'

import type { Permission } from '../../api/types'
import { LoadingState } from '../../components/common'
import { can } from '../../domain-ui/roles'
import { useAuth } from './AuthProvider'

/** Exige sesión iniciada; si no, envía al login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status === 'loading') return <LoadingState label="Verificando sesión…" />
  if (status === 'anonymous') return <Navigate to="/login" replace />
  return <>{children}</>
}

/**
 * Oculta/avisa por permiso para mejorar la experiencia. NO es un control de seguridad: el
 * backend verifica permisos y pertenencia al tenant en cada solicitud.
 */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission
  children: ReactNode
}) {
  const { user } = useAuth()
  if (!user || !can(user.permissions, permission)) {
    return (
      <div className="alert alert-error" role="alert">
        <strong>Permisos insuficientes</strong>
        <p>Su rol no tiene acceso a esta pantalla.</p>
        <Link to="/">Volver al inicio</Link>
      </div>
    )
  }
  return <>{children}</>
}
