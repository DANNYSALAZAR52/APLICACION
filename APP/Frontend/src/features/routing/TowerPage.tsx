import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import type { AlertOut, RoutingVehicle } from '../../api/types'
import { Badge, Card } from '../../components/common'
import { formatDateTime, formatInt } from '../../domain-ui/format'
import {
  INCIDENT_LABELS,
  KIND_LABELS,
  STOP_KIND_LABELS,
  STOP_STATE_LABELS,
  colorOfVehicle,
  formatClock,
  formatMinutes,
  vehicleStatusLabel,
  windowText,
} from '../../domain-ui/routing'
import { ClockControls } from './ClockControls'
import { FleetMap } from './FleetMap'
import { useRouting } from './RoutingProvider'

const ALERT_TONE = { critical: 'bad', warning: 'warn', info: 'neutral' } as const
const ALERT_TITLE = { critical: 'Crítica', warning: 'Atención', info: 'Aviso' } as const

export function AlertList({ alerts }: { alerts: AlertOut[] }) {
  if (alerts.length === 0) {
    return <p className="muted">Sin alertas: todas las entregas llegan dentro de su ventana.</p>
  }
  return (
    <ul className="alert-list" aria-label="Alertas del día">
      {alerts.map((a, i) => (
        <li key={`${a.code}-${i}`}>
          <Badge tone={ALERT_TONE[a.level]}>{ALERT_TITLE[a.level]}</Badge> {a.message}
        </li>
      ))}
    </ul>
  )
}

export function RoutingNotices() {
  const { snapshot, notice, actionError, clearNotice } = useRouting()
  if (!snapshot) return null
  return (
    <>
      {snapshot.travel_notice ? (
        <div className="alert alert-warn" role="status">
          <strong>{snapshot.travel_notice}.</strong> El proveedor de tiempos no responde: se usa el
          perfil de velocidades por hora y los cierres conocidos. No hay información de tráfico en
          vivo.
        </div>
      ) : null}
      {actionError ? (
        <div className="alert alert-error" role="alert">
          {actionError}{' '}
          <button type="button" className="btn btn-small" onClick={clearNotice}>
            Cerrar
          </button>
        </div>
      ) : null}
      {notice ? (
        <div className="alert alert-ok" role="status">
          {notice}{' '}
          <button type="button" className="btn btn-small" onClick={clearNotice}>
            Entendido
          </button>
        </div>
      ) : null}
    </>
  )
}

function GpsCell({ v }: { v: RoutingVehicle }) {
  if (v.gps_status === 'n/a') return <span className="muted">—</span>
  const age = v.gps_age_min === null ? '' : ` · última posición hace ${Math.round(v.gps_age_min)} min`
  return v.gps_status === 'no_signal' ? (
    <Badge tone="bad">Sin señal{age}</Badge>
  ) : (
    <Badge tone="ok">Señal OK{age}</Badge>
  )
}

export function TowerPage() {
  const { snapshot, live, busy, control } = useRouting()
  const [selected, setSelected] = useState('all')
  const stops = useMemo(
    () =>
      (snapshot?.stops ?? [])
        .filter((s) => selected === 'all' || s.vehicle_id === selected)
        .sort((a, b) => a.plate.localeCompare(b.plate) || a.sequence - b.sequence),
    [snapshot, selected],
  )
  if (!snapshot) return null
  const { plan, vehicles, clock } = snapshot
  const pendingProposals = snapshot.proposals.filter((p) => p.status === 'pending')

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Torre de control</h1>
          <p className="muted">
            Plan versión <strong>{plan.version}</strong> · {plan.reason} · creado{' '}
            {formatDateTime(plan.created_at)} por {plan.created_by}
          </p>
        </div>
        <div className="actions">
          <Badge tone={live ? 'ok' : 'neutral'}>
            {live ? 'Tiempo real conectado' : 'Actualizando por consulta periódica'}
          </Badge>
          <Link className="btn" to="/eventos">
            Eventos y re-ruteo
            {pendingProposals.length > 0 ? ` (${pendingProposals.length} por decidir)` : ''}
          </Link>
          <Link className="btn" to="/linea-de-tiempo">
            Línea de tiempo
          </Link>
        </div>
      </div>

      <RoutingNotices />

      <div className="stats">
        <div className="stat">
          <div className="stat-label">Hora simulada</div>
          <div className="stat-value">{formatClock(clock.minute)}</div>
          <div className="stat-note muted">{clock.paused ? 'Reloj en pausa' : `Corre a ${clock.speed}×`}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Entregas en riesgo o tarde</div>
          <div className="stat-value">{formatInt(plan.late_stops)}</div>
          <div className="stat-note muted">{formatMinutes(plan.delay_min)} de retraso proyectado</div>
        </div>
        <div className="stat">
          <div className="stat-label">Vehículos en operación</div>
          <div className="stat-value">{formatInt(plan.vehicles_in_use)}</div>
          <div className="stat-note muted">de {formatInt(vehicles.length)} disponibles</div>
        </div>
        <div className="stat">
          <div className="stat-label">Pedidos sin asignar</div>
          <div className="stat-value">{formatInt(plan.unassigned)}</div>
          <div className="stat-note muted">Motor: {plan.engine}</div>
        </div>
      </div>

      <div className="tower-grid">
        <Card title="Mapa" id="map">
          <FleetMap snapshot={snapshot} />
          <p className="muted small">
            Trayectos en línea recta entre paradas (DEMO-ONLY, no siguen las calles). Vehículo:
            etiqueta con la placa. Gris: entregada · rojo: en riesgo · línea punteada: hacia la
            siguiente parada.
          </p>
        </Card>
        <div className="side-stack">
          <ClockControls />
          <Card title="Alertas" id="alerts">
            <AlertList alerts={snapshot.alerts} />
          </Card>
          <Card title="Novedades de los conductores" id="reports">
            {snapshot.reports.length === 0 ? (
              <p className="muted">Sin novedades reportadas.</p>
            ) : (
              <ul className="plain">
                {snapshot.reports.map((r) => (
                  <li key={r.id}>
                    <strong>
                      {formatClock(r.minute)} · {r.plate}
                    </strong>{' '}
                    — {INCIDENT_LABELS[r.kind]}
                    {r.order_id ? ` (pedido ${r.order_id})` : ''}: {r.detail}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Card title="Vehículos" id="vehicles">
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Estado de los vehículos</caption>
            <thead>
              <tr>
                <th scope="col">Placa</th>
                <th scope="col">Tipo</th>
                <th scope="col">Estado</th>
                <th scope="col" className="num">
                  Entregadas
                </th>
                <th scope="col" className="num">
                  Pendientes
                </th>
                <th scope="col">Siguiente parada</th>
                <th scope="col" className="num">
                  Carga (kg)
                </th>
                <th scope="col">Regreso al CEDI</th>
                <th scope="col">Retraso proyectado</th>
                <th scope="col">GPS</th>
                <th scope="col">Simulación</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr key={v.id}>
                  <th scope="row">
                    <span
                      className="swatch"
                      style={{ background: colorOfVehicle(vehicles, v.id) }}
                      aria-hidden="true"
                    />
                    {v.plate}
                  </th>
                  <td>{KIND_LABELS[v.kind]}</td>
                  <td>
                    {v.status === 'broken' ? (
                      <Badge tone="bad">{vehicleStatusLabel(v.status)}</Badge>
                    ) : (
                      vehicleStatusLabel(v.status)
                    )}
                  </td>
                  <td className="num">{formatInt(v.completed_stops)}</td>
                  <td className="num">{formatInt(v.pending_stops)}</td>
                  <td>
                    {v.next_stop_label
                      ? `${v.next_stop_label} (${formatClock(v.next_eta_min)})`
                      : '—'}
                  </td>
                  <td className="num">
                    {formatInt(v.load_kg)} / {formatInt(v.capacity_kg)}
                  </td>
                  <td>{formatClock(v.return_min)}</td>
                  <td>
                    {v.delay_min > 0 ? (
                      <Badge tone="bad">
                        {formatMinutes(v.delay_min)} · {v.late_stops} tarde
                      </Badge>
                    ) : (
                      <Badge tone="ok">A tiempo</Badge>
                    )}
                  </td>
                  <td>
                    <GpsCell v={v} />
                  </td>
                  <td>
                    {v.route_status === 'active' ? (
                      <button
                        type="button"
                        className="btn btn-small"
                        disabled={busy}
                        aria-label={`${v.gps_signal_enabled ? 'Cortar' : 'Restablecer'} la señal GPS de ${v.plate}`}
                        onClick={() => void control('gps_signal', v.gps_signal_enabled ? 0 : 1, v.id)}
                      >
                        {v.gps_signal_enabled ? 'Cortar señal' : 'Restablecer señal'}
                      </button>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Paradas" id="stops">
        <div className="field inline">
          <label htmlFor="stops-filter">Vehículo</label>
          <select id="stops-filter" value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="all">Todos</option>
            {vehicles
              .filter((v) => v.route_status !== 'standby')
              .map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate}
                </option>
              ))}
          </select>
        </div>
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Paradas del plan vigente</caption>
            <thead>
              <tr>
                <th scope="col">Vehículo</th>
                <th scope="col" className="num">
                  #
                </th>
                <th scope="col">Parada</th>
                <th scope="col">Pedido</th>
                <th scope="col">Ventana</th>
                <th scope="col">Llegada</th>
                <th scope="col">Salida</th>
                <th scope="col">Estado</th>
              </tr>
            </thead>
            <tbody>
              {stops.map((s) => (
                <tr key={`${s.vehicle_id}-${s.key}-${s.sequence}`}>
                  <td>{s.plate}</td>
                  <td className="num">{s.sequence}</td>
                  <td>
                    {s.label}
                    {s.kind !== 'delivery' ? (
                      <span className="muted"> · {STOP_KIND_LABELS[s.kind]}</span>
                    ) : null}
                  </td>
                  <td>{s.order_id ?? '—'}</td>
                  <td>{windowText(s)}</td>
                  <td>{formatClock(s.arrival_min)}</td>
                  <td>{formatClock(s.departure_min)}</td>
                  <td>
                    {s.delay_min > 0 ? (
                      <Badge tone="bad">Tarde {formatMinutes(s.delay_min)}</Badge>
                    ) : s.at_risk ? (
                      <Badge tone="warn">En riesgo</Badge>
                    ) : s.state === 'completed' ? (
                      <Badge tone="ok">{STOP_STATE_LABELS[s.state]}</Badge>
                    ) : (
                      STOP_STATE_LABELS[s.state]
                    )}
                    {s.confirmed_by ? (
                      <div className="muted small">
                        Confirmada {s.confirmed_by === 'geofence' ? 'por geocerca' : 'por el conductor'} a las{' '}
                        {formatClock(s.confirmed_min)}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {snapshot.unassigned.length > 0 ? (
          <div className="alert alert-error" role="alert">
            <strong>Pedidos sin asignar</strong>
            <ul className="plain">
              {snapshot.unassigned.map((u) => (
                <li key={u.order_id}>
                  {u.order_id} ({u.customer_code}): {u.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Card>
    </div>
  )
}
