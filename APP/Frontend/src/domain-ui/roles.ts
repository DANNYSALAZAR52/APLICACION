import type { Permission, Role } from '../api/types'

export const ROLE_LABELS: Record<Role, string> = {
  management: 'Gerencia de operaciones',
  dispatcher: 'Despachador',
  driver: 'Conductor',
  tenant_admin: 'Administrador de la empresa',
  super_admin: 'Superadministrador',
}

export const roleLabel = (role: Role): string => ROLE_LABELS[role] ?? role

/**
 * Ocultar opciones por permiso mejora la experiencia pero NO es un control de seguridad: el
 * backend aplica RBAC y pertenencia al tenant en cada operación.
 */
export const can = (permissions: readonly Permission[], needed: Permission): boolean =>
  permissions.includes(needed)

export const ACTION_LABELS: Record<string, string> = {
  'auth.login': 'Inicio de sesión',
  'auth.refresh': 'Renovación de sesión',
  'auth.logout': 'Cierre de sesión',
  'capacity.dashboard.view': 'Consulta del tablero de capacidad',
  'tenant.list': 'Consulta de empresas',
  'tenant.provision': 'Alta de empresa',
  'tenant.suspend': 'Suspensión de empresa',
  'tenant.reactivate': 'Reactivación de empresa',
}

export const actionLabel = (action: string): string => ACTION_LABELS[action] ?? action

export const OUTCOME_LABELS = {
  success: 'Correcto',
  denied: 'Denegado',
  failure: 'Fallido',
} as const
