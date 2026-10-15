import { Outlet } from 'react-router-dom'

import { ErrorState, LoadingState } from '../../components/common'
import { RoutingProvider, useRouting } from './RoutingProvider'

function Gate() {
  const { snapshot, error, loading, refresh } = useRouting()
  if (loading && !snapshot) return <LoadingState label="Preparando el plan de la mañana…" />
  if (!snapshot) return <ErrorState error={error} onRetry={refresh} />
  return <Outlet />
}

/** Comparte un único estado del día entre torre de control, línea de tiempo y eventos. */
export function RoutingLayout() {
  return (
    <RoutingProvider>
      <Gate />
    </RoutingProvider>
  )
}
