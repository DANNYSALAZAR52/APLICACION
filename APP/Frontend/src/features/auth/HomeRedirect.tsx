import { Navigate } from 'react-router-dom'

import { NAV_ITEMS } from '../../app/Shell'
import { can } from '../../domain-ui/roles'
import { useAuth } from './AuthProvider'

/** Lleva a la primera pantalla disponible para el rol; si no hay ninguna, a "Próximamente". */
export function HomeRedirect() {
  const { user } = useAuth()
  const first = NAV_ITEMS.find((item) => user && can(user.permissions, item.permission))
  return <Navigate to={first?.to ?? '/proximamente'} replace />
}
