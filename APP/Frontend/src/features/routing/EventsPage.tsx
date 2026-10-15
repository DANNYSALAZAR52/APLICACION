import { Link } from 'react-router-dom'

import { Badge, Card, EmptyState } from '../../components/common'
import { formatDateTime, formatDecimal } from '../../domain-ui/format'
import { EVENT_LABELS, formatClock } from '../../domain-ui/routing'
import { EventForm } from './EventForm'
import { ProposalCard } from './ProposalCard'
import { useRouting } from './RoutingProvider'
import { RoutingNotices } from './TowerPage'
import { VersionCompare } from './VersionCompare'

/** Registro de eventos, propuestas de re-ruteo y aprobación/rechazo (pantalla 3). */
export function EventsPage() {
  const { snapshot } = useRouting()
  if (!snapshot) return null
  const pending = snapshot.proposals.filter((p) => p.status === 'pending')
  const decided = snapshot.proposals.filter((p) => p.status !== 'pending')
  const engines = snapshot.versions[0]?.comparison ?? []

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Eventos y re-ruteo</h1>
          <p className="muted">
            Hora simulada {formatClock(snapshot.clock.minute)} · plan versión {snapshot.plan.version}.
            Cada re-ruteo aprobado crea una versión nueva con su motivo, responsable y fecha; las
            anteriores no se modifican.
          </p>
        </div>
        <Link className="btn" to="/torre-de-control">
          Volver a la torre de control
        </Link>
      </div>
      <RoutingNotices />

      <Card title="Inyectar evento" id="inject">
        <EventForm snapshot={snapshot} key={snapshot.plan.version} />
      </Card>

      <Card title={`Propuestas por decidir (${pending.length})`} id="pending">
        {snapshot.clock.paused && pending.length > 0 ? (
          <p className="muted small">
            El reloj se pausó para que usted decida. Reanúdelo desde la torre de control.
          </p>
        ) : null}
        {pending.length === 0 ? (
          <EmptyState title="No hay propuestas pendientes">
            Inyecte un evento o espere a que el seguimiento detecte un retraso.
          </EmptyState>
        ) : (
          pending.map((p) => <ProposalCard key={p.id} proposal={p} />)
        )}
      </Card>

      <Card title="Registro de eventos" id="log">
        {snapshot.events.length === 0 ? (
          <EmptyState title="Sin eventos todavía" />
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Eventos operativos del día</caption>
              <thead>
                <tr>
                  <th scope="col">Hora</th>
                  <th scope="col">Evento</th>
                  <th scope="col">Registrado por</th>
                  <th scope="col">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.events.map((e) => (
                  <tr key={e.id}>
                    <td>{formatClock(e.minute)}</td>
                    <td>
                      <Badge tone="neutral">{EVENT_LABELS[e.type]}</Badge> {e.summary}
                    </td>
                    <td>{e.created_by}</td>
                    <td>{e.outcome || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {decided.length > 0 ? (
        <Card title="Propuestas resueltas" id="decided">
          {decided.map((p) => (
            <ProposalCard key={p.id} proposal={p} />
          ))}
        </Card>
      ) : null}

      <Card title="Versiones del plan" id="versions">
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Versiones del plan</caption>
            <thead>
              <tr>
                <th scope="col" className="num">Versión</th>
                <th scope="col">Motivo</th>
                <th scope="col">Responsable</th>
                <th scope="col">Creada</th>
                <th scope="col" className="num">Entregas tarde</th>
                <th scope="col" className="num">Puntaje</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.versions.map((v) => (
                <tr key={v.version}>
                  <th scope="row" className="num">
                    {v.version}
                    {v.version === snapshot.plan.version ? ' (vigente)' : ''}
                  </th>
                  <td>{v.reason}</td>
                  <td>{v.created_by}</td>
                  <td>{formatDateTime(v.created_at)}</td>
                  <td className="num">{v.late_stops}</td>
                  <td className="num">{Math.round(v.score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>Comparar versiones</h3>
        <VersionCompare versions={snapshot.versions} key={snapshot.versions.length} />
        {engines.length > 0 ? (
          <>
            <h3>Motores del plan inicial (versión 1)</h3>
            <p className="muted small">
              Se comparan sin asumir que uno gana siempre: se descarta cualquier plan que viole la
              capacidad y se elige el de menos pedidos sin asignar y, a igualdad, el de menor puntaje.
            </p>
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Comparación de motores de ruteo</caption>
                <thead>
                  <tr>
                    <th scope="col">Motor</th>
                    <th scope="col" className="num">Puntaje</th>
                    <th scope="col" className="num">Asignados</th>
                    <th scope="col" className="num">Sin asignar</th>
                    <th scope="col" className="num">Tiempo (s)</th>
                    <th scope="col">Elegido</th>
                  </tr>
                </thead>
                <tbody>
                  {engines.map((e) => (
                    <tr key={e.engine}>
                      <th scope="row">{e.engine}</th>
                      <td className="num">{formatDecimal(e.score)}</td>
                      <td className="num">{e.assigned_orders}</td>
                      <td className="num">{e.unassigned_orders}</td>
                      <td className="num">{formatDecimal(e.elapsed_s)}</td>
                      <td>{e.chosen ? <Badge tone="ok">Elegido</Badge> : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </Card>
    </div>
  )
}
