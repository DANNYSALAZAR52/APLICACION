import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../../components/common'
import { formatDateTime } from '../../domain-ui/format'
import { OUTCOME_LABELS, actionLabel } from '../../domain-ui/roles'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'

const TONE = { success: 'ok', denied: 'warn', failure: 'bad' } as const

export function AuditPage() {
  const { client, user } = useAuth()
  const { state, reload } = useApiResource((signal) => client.audit(signal))
  const scope = user?.role === 'super_admin' ? 'de todas las empresas' : 'de su empresa'

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Auditoría</h1>
          <p className="muted">
            Últimos eventos {scope}: quién, qué, cuándo y con qué resultado. No incluyen secretos.
          </p>
        </div>
        <button type="button" className="btn" onClick={reload}>
          Actualizar
        </button>
      </div>
      <Card id="audit">
        {state.status === 'loading' ? <LoadingState label="Cargando eventos…" /> : null}
        {state.status === 'error' ? <ErrorState error={state.error} onRetry={reload} /> : null}
        {state.status === 'success' && state.data.length === 0 ? (
          <EmptyState title="Sin eventos registrados" />
        ) : null}
        {state.status === 'success' && state.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Eventos de auditoría</caption>
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Acción</th>
                  <th scope="col">Usuario</th>
                  <th scope="col">Resultado</th>
                  <th scope="col">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((event, index) => (
                  <tr key={`${event.at}-${index}`}>
                    <td>{formatDateTime(event.at)}</td>
                    <td>{actionLabel(event.action)}</td>
                    <td>{event.actor_username ?? '—'}</td>
                    <td>
                      <Badge tone={TONE[event.outcome]}>{OUTCOME_LABELS[event.outcome]}</Badge>
                    </td>
                    <td className="muted small">
                      {Object.entries(event.detail)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(' · ') || event.resource || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  )
}
