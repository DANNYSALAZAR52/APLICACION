import { PENDING_ITEMS } from '../../app/Shell'
import { Card } from '../../components/common'
import { can } from '../../domain-ui/roles'
import { useAuth } from './AuthProvider'

export function PendingPage() {
  const { user } = useAuth()
  const mine = PENDING_ITEMS.filter((item) => user && can(user.permissions, item.permission))
  return (
    <Card title="Pantallas en construcción" id="pending">
      <p>
        Las pantallas de su rol se construyen en fases posteriores del demo. Hoy están disponibles
        la <strong>capacidad de flota</strong> (gerencia), la <strong>administración de empresas</strong>{' '}
        (superadministrador) y la <strong>auditoría</strong> (administradores).
      </p>
      {mine.length > 0 ? (
        <>
          <p>Pantallas suyas pendientes:</p>
          <ul>
            {mine.map((item) => (
              <li key={item.label}>{item.label}</li>
            ))}
          </ul>
        </>
      ) : null}
    </Card>
  )
}
