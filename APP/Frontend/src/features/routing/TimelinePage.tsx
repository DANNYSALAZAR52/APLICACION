import { useMemo } from 'react'
import { Link } from 'react-router-dom'

import type { RoutingStop, RoutingVehicle } from '../../api/types'
import { Badge, Card, EmptyState } from '../../components/common'
import {
  STOP_KIND_LABELS,
  colorOfVehicle,
  formatClock,
  formatMinutes,
  windowText,
} from '../../domain-ui/routing'
import { useRouting } from './RoutingProvider'
import { RoutingNotices } from './TowerPage'

const LEFT = 96
const WIDTH = 1040
const ROW = 52
const TOP = 28

function range(stops: RoutingStop[], vehicles: RoutingVehicle[], now: number): [number, number] {
  const starts = [now, ...stops.map((s) => s.arrival_min)]
  const ends = [
    now,
    ...stops.map((s) => s.departure_min),
    ...vehicles.map((v) => v.return_min ?? 0),
  ]
  const lo = Math.floor(Math.min(...starts, 6 * 60) / 60) * 60
  const hi = Math.ceil(Math.max(...ends, 17 * 60) / 60) * 60
  return [lo, hi]
}

/** Línea de tiempo por vehículo (pantalla 2): cada parada con espera, servicio y ventana. */
export function TimelinePage() {
  const { snapshot } = useRouting()
  const rows = useMemo(
    () => (snapshot ? snapshot.vehicles.filter((v) => v.route_status !== 'standby') : []),
    [snapshot],
  )
  if (!snapshot) return null
  const { stops, clock, vehicles } = snapshot
  const [lo, hi] = range(stops, vehicles, clock.minute)
  const x = (minute: number) => LEFT + ((minute - lo) / (hi - lo)) * (WIDTH - LEFT - 12)
  const height = TOP + rows.length * ROW + 24
  const hours: number[] = []
  for (let m = lo; m <= hi; m += 60) hours.push(m)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Línea de tiempo por vehículo</h1>
          <p className="muted">
            Plan versión {snapshot.plan.version} · hora simulada {formatClock(clock.minute)}. Cada
            bloque va de la llegada a la salida de la parada; la franja clara es espera por ventana
            y la línea inferior es la ventana de entrega.
          </p>
        </div>
        <Link className="btn" to="/torre-de-control">
          Volver a la torre de control
        </Link>
      </div>
      <RoutingNotices />

      {rows.length === 0 ? (
        <EmptyState title="Sin rutas en operación">No hay vehículos con paradas hoy.</EmptyState>
      ) : (
        <Card title="Horarios" id="timeline">
          <div className="table-wrap">
            <svg
              viewBox={`0 0 ${WIDTH} ${height}`}
              className="timeline"
              role="img"
              aria-label="Línea de tiempo de paradas por vehículo; la misma información está en la tabla inferior"
            >
              {hours.map((m) => (
                <g key={m}>
                  <line x1={x(m)} x2={x(m)} y1={TOP - 6} y2={height - 18} className="tl-grid" />
                  <text x={x(m)} y={14} textAnchor="middle" className="tl-hour">
                    {formatClock(m)}
                  </text>
                </g>
              ))}
              {rows.map((v, i) => {
                const y = TOP + i * ROW
                const color = colorOfVehicle(vehicles, v.id)
                const mine = stops.filter((s) => s.vehicle_id === v.id)
                return (
                  <g key={v.id}>
                    <text x={6} y={y + 22} className="tl-label">
                      {v.plate}
                    </text>
                    <line x1={LEFT} x2={WIDTH - 12} y1={y + 18} y2={y + 18} className="tl-lane" />
                    {mine.map((s) => {
                      const fill =
                        s.state === 'completed' ? '#9aa3af' : s.delay_min > 0 ? '#dc2626' : s.at_risk ? '#f59e0b' : color
                      return (
                        <g key={`${s.key}-${s.sequence}`}>
                          {s.service_start_min > s.arrival_min ? (
                            <rect
                              x={x(s.arrival_min)}
                              y={y + 8}
                              width={Math.max(1, x(s.service_start_min) - x(s.arrival_min))}
                              height={20}
                              className="tl-wait"
                            />
                          ) : null}
                          <rect
                            x={x(s.service_start_min)}
                            y={y + 8}
                            width={Math.max(3, x(s.departure_min) - x(s.service_start_min))}
                            height={20}
                            rx={3}
                            fill={fill}
                            stroke={s.delay_min > 0 ? '#7f1d1d' : 'none'}
                            strokeWidth={s.delay_min > 0 ? 2 : 0}
                          >
                            <title>
                              {`${s.label} (${STOP_KIND_LABELS[s.kind]}): llegada ${formatClock(s.arrival_min)}, salida ${formatClock(s.departure_min)}, ventana ${windowText(s)}${s.delay_min > 0 ? `, retraso ${Math.round(s.delay_min)} min` : ''}`}
                            </title>
                          </rect>
                          {s.window_start_min !== null && s.window_end_min !== null ? (
                            <line
                              x1={x(s.window_start_min)}
                              x2={x(s.window_end_min)}
                              y1={y + 36}
                              y2={y + 36}
                              className="tl-window"
                            />
                          ) : null}
                        </g>
                      )
                    })}
                    {v.return_min !== null ? (
                      <text x={x(v.return_min)} y={y + 46} textAnchor="middle" className="tl-return">
                        ⌂ {formatClock(v.return_min)}
                      </text>
                    ) : null}
                  </g>
                )
              })}
              <line x1={x(clock.minute)} x2={x(clock.minute)} y1={TOP - 8} y2={height - 18} className="tl-now" />
              <text x={x(clock.minute)} y={height - 4} textAnchor="middle" className="tl-now-label">
                Ahora {formatClock(clock.minute)}
              </text>
            </svg>
          </div>
          <p className="muted small">
            Colores por vehículo · gris: entregada · rojo con borde: llega tarde · naranja: en
            riesgo · ⌂ hora de regreso al CEDI.
          </p>
        </Card>
      )}

      {rows.map((v) => {
        const mine = stops.filter((s) => s.vehicle_id === v.id)
        return (
          <details key={v.id} className="card tl-details">
            <summary>
              <strong>{v.plate}</strong> · {mine.length} parada(s) · regreso {formatClock(v.return_min)}{' '}
              {v.delay_min > 0 ? <Badge tone="bad">{formatMinutes(v.delay_min)} de retraso</Badge> : null}
            </summary>
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Paradas de {v.plate}</caption>
                <thead>
                  <tr>
                    <th scope="col" className="num">#</th>
                    <th scope="col">Parada</th>
                    <th scope="col">Ventana</th>
                    <th scope="col">Llegada</th>
                    <th scope="col">Espera</th>
                    <th scope="col">Salida</th>
                    <th scope="col">Retraso</th>
                  </tr>
                </thead>
                <tbody>
                  {mine.map((s) => (
                    <tr key={`${s.key}-${s.sequence}`}>
                      <td className="num">{s.sequence}</td>
                      <td>{s.label}</td>
                      <td>{windowText(s)}</td>
                      <td>{formatClock(s.arrival_min)}</td>
                      <td>{s.wait_min > 0 ? formatMinutes(s.wait_min) : '—'}</td>
                      <td>{formatClock(s.departure_min)}</td>
                      <td>{s.delay_min > 0 ? formatMinutes(s.delay_min) : 'A tiempo'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )
      })}
    </div>
  )
}
