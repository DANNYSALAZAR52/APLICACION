import type { KpiOut, ScenarioOut } from '../../api/types'
import { Badge, Card, ErrorState, LoadingState } from '../../components/common'
import { formatInt, formatPercent } from '../../domain-ui/format'
import { formatClock, formatMinutes } from '../../domain-ui/routing'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'

// Dos series con colores validados para daltonismo; además se rotulan con texto y valor.
const PUNCTUALITY = '#0072B2'
const OTIF = '#D55E00'

const pct = (value: number | null): string => formatPercent(value)

function Bars({ scenarios }: { scenarios: ScenarioOut[] }) {
  return (
    <div className="kbars" role="img" aria-label="Puntualidad y OTIF por escenario; los mismos valores están en la tabla">
      <ul className="kbars-legend" aria-label="Leyenda">
        <li>
          <span className="swatch" style={{ background: PUNCTUALITY }} aria-hidden="true" /> Puntualidad
        </li>
        <li>
          <span className="swatch" style={{ background: OTIF }} aria-hidden="true" /> OTIF
        </li>
      </ul>
      {scenarios.map((s) => (
        <div key={s.key} className="kbars-row">
          <div className="kbars-title">{s.title}</div>
          {(
            [
              ['Puntualidad', s.kpis.punctuality, PUNCTUALITY],
              ['OTIF', s.kpis.otif, OTIF],
            ] as const
          ).map(([label, value, color]) => (
            <div
              key={label}
              className="kbar"
              title={`${s.title} · ${label}: ${pct(value)}`}
            >
              <span className="kbar-label">{label}</span>
              <span className="kbar-track">
                <span
                  className="kbar-fill"
                  style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%`, background: color }}
                />
              </span>
              <span className="kbar-value">{pct(value)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function KpiStats({ k }: { k: KpiOut }) {
  return (
    <div className="stats">
      <div className="stat">
        <div className="stat-label">Puntualidad</div>
        <div className="stat-value">{pct(k.punctuality)}</div>
        <div className="stat-note muted">
          {formatInt(k.on_time_orders)} de {formatInt(k.committed_orders)} pedidos a tiempo
        </div>
      </div>
      <div className="stat">
        <div className="stat-label">OTIF</div>
        <div className="stat-value">{pct(k.otif)}</div>
        <div className="stat-note muted">
          {formatInt(k.otif_orders)} de {formatInt(k.committed_orders)} completos y a tiempo
        </div>
      </div>
      <div className="stat">
        <div className="stat-label">Retraso total</div>
        <div className="stat-value">{formatMinutes(k.total_delay_min)}</div>
        <div className="stat-note muted">{formatInt(k.late_orders)} entrega(s) tarde</div>
      </div>
      <div className="stat">
        <div className="stat-label">Pedidos sin atender</div>
        <div className="stat-value">{formatInt(k.unattended_orders)}</div>
        <div className="stat-note muted">Cuentan como no cumplidos</div>
      </div>
    </div>
  )
}

function Comparison({ scenarios }: { scenarios: ScenarioOut[] }) {
  const stat = scenarios.find((s) => s.key === 'static_events')
  const dyn = scenarios.find((s) => s.key === 'dynamic_events')
  if (!stat || !dyn) return null
  const moreDelivered = dyn.kpis.delivered_orders - stat.kpis.delivered_orders
  const otifDelta = (dyn.kpis.otif ?? 0) - (stat.kpis.otif ?? 0)
  const lateDelta = dyn.kpis.late_orders - stat.kpis.late_orders
  return (
    <div className="alert alert-ok" role="status">
      <strong>Con los mismos eventos y el mismo denominador ({formatInt(dyn.kpis.committed_orders)} pedidos):</strong>
      <ul className="plain">
        <li>
          El ruteo dinámico entrega {formatInt(dyn.kpis.delivered_orders)} pedidos frente a{' '}
          {formatInt(stat.kpis.delivered_orders)} del plan estático
          {moreDelivered > 0 ? ` (${formatInt(moreDelivered)} más)` : ''}.
        </li>
        <li>
          OTIF {pct(dyn.kpis.otif)} frente a {pct(stat.kpis.otif)} (
          {otifDelta >= 0 ? '+' : '−'}
          {formatPercent(Math.abs(otifDelta))} de diferencia).
        </li>
        <li>
          Entregas tarde: {formatInt(dyn.kpis.late_orders)} frente a {formatInt(stat.kpis.late_orders)}
          {lateDelta > 0
            ? '. Hay más porque se entregan pedidos que el plan estático nunca atendió, y algunos llegan fuera de ventana.'
            : '.'}
        </li>
        <li>
          Costo: {formatInt(dyn.plan_versions)} versiones del plan y {formatInt(dyn.reserve_activations)}{' '}
          reserva(s) o tercero(s) activados.
        </li>
      </ul>
    </div>
  )
}

/** Indicadores diarios (pantalla 7): en vivo y comparación plan estático vs. ruteo dinámico. */
export function IndicatorsPage() {
  const { client } = useAuth()
  const { state, reload } = useApiResource((signal) => client.indicators(signal))

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Indicadores diarios</h1>
          <p className="muted">
            Puntualidad y OTIF son métricas distintas y comparten el mismo denominador.
          </p>
        </div>
        <button type="button" className="btn" onClick={reload}>
          Actualizar
        </button>
      </div>

      {state.status === 'loading' ? (
        <LoadingState label="Calculando indicadores y escenarios (la primera vez toma unos segundos)…" />
      ) : null}
      {state.status === 'error' ? <ErrorState error={state.error} onRetry={reload} /> : null}

      {state.status === 'success' ? (
        <>
          <Card title="Hoy: proyección al cierre con el plan vigente" id="live">
            <p className="muted">
              Plan versión {state.data.live.plan_version} · hora simulada {formatClock(state.data.live.minute)} ·{' '}
              {formatInt(state.data.live.delivered_so_far)} entregas hechas hasta ahora (
              {formatInt(state.data.live.on_time_so_far)} a tiempo).
            </p>
            <KpiStats k={state.data.live.projected} />
          </Card>

          <Card title="Escenarios de ejemplo: plan estático vs. ruteo dinámico" id="scenarios">
            <p className="muted">
              <Badge tone="warn">Simulación</Badge> Se ejecutan con datos sintéticos y el mismo guion de
              eventos (cierre vial, cambio de ventana, pedido urgente y avería). No son mediciones reales.
            </p>
            <Comparison scenarios={state.data.scenarios} />
            <Bars scenarios={state.data.scenarios} />
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Indicadores por escenario</caption>
                <thead>
                  <tr>
                    <th scope="col">Escenario</th>
                    <th scope="col" className="num">Comprometidos</th>
                    <th scope="col" className="num">Entregados</th>
                    <th scope="col" className="num">A tiempo</th>
                    <th scope="col" className="num">Tarde</th>
                    <th scope="col" className="num">Sin atender</th>
                    <th scope="col" className="num">Incompletas</th>
                    <th scope="col" className="num">Retraso total</th>
                    <th scope="col" className="num">Puntualidad</th>
                    <th scope="col" className="num">OTIF</th>
                    <th scope="col" className="num">Versiones</th>
                    <th scope="col" className="num">Reservas</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.scenarios.map((s) => (
                    <tr key={s.key}>
                      <th scope="row">
                        {s.title}
                        <div className="muted small">{s.description}</div>
                      </th>
                      <td className="num">{formatInt(s.kpis.committed_orders)}</td>
                      <td className="num">{formatInt(s.kpis.delivered_orders)}</td>
                      <td className="num">{formatInt(s.kpis.on_time_orders)}</td>
                      <td className="num">{formatInt(s.kpis.late_orders)}</td>
                      <td className="num">{formatInt(s.kpis.unattended_orders)}</td>
                      <td className="num">{formatInt(s.kpis.incomplete_orders)}</td>
                      <td className="num">{formatMinutes(s.kpis.total_delay_min)}</td>
                      <td className="num">{pct(s.kpis.punctuality)}</td>
                      <td className="num">{pct(s.kpis.otif)}</td>
                      <td className="num">{formatInt(s.plan_versions)}</td>
                      <td className="num">{formatInt(s.reserve_activations)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Definiciones" id="definitions">
            <ul className="plain">
              {state.data.definitions.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}
    </div>
  )
}
