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
        Su rol no tiene pantallas disponibles en este demo. Consulte con el administrador de su
        empresa si debería tener acceso a alguna.
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
