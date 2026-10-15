import type { DashboardResponse } from '../../api/types'
import { Card, EmptyState } from '../../components/common'
import {
  NOT_AVAILABLE,
  formatDecimal,
  formatInt,
  formatPercent,
  vehicleLabel,
} from '../../domain-ui/format'

export function CorridorsPanel({ data }: { data: DashboardResponse }) {
  return (
    <Card title="Detalle por corredor" id="corridors">
      <p className="muted small">
        Demanda de diseño = percentil P{Math.round(data.parameters.design_percentile * 100)} de los
        últimos {data.parameters.window_days} días con dato (los días sin dato no cuentan como cero).
      </p>
      {data.corridors.length === 0 ? (
        <EmptyState title="Sin corredores con datos suficientes" />
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Demanda, ciclo y capacidad por corredor</caption>
            <thead>
              <tr>
                <th scope="col">Corredor</th>
                <th scope="col">Tipo</th>
                <th scope="col" className="num">Demanda diseño (t/día)</th>
                <th scope="col" className="num">Promedio</th>
                <th scope="col" className="num">Desv. est.</th>
                <th scope="col" className="num">Días válidos</th>
                <th scope="col" className="num">Ciclo (h)</th>
                <th scope="col" className="num">Capacidad efectiva (t/día)</th>
                <th scope="col" className="num">Ciclo Lean (h)</th>
                <th scope="col" className="num">Valor agregado</th>
                <th scope="col" className="num">Muda</th>
              </tr>
            </thead>
            <tbody>
              {data.corridors.map((c) => (
                <tr key={c.code}>
                  <th scope="row">
                    {c.code}
                    <div className="muted small">{c.name}</div>
                  </th>
                  <td>{vehicleLabel(c.vehicle_type)}</td>
                  <td className="num">{formatDecimal(c.design_t)}</td>
                  <td className="num">{formatDecimal(c.mean_t)}</td>
                  <td className="num">{formatDecimal(c.std_t)}</td>
                  <td className="num">{formatInt(c.valid_days)}</td>
                  <td className="num">{formatDecimal(c.cycle_h)}</td>
                  <td className="num">{formatDecimal(c.effective_t_per_day)}</td>
                  <td className="num">{formatDecimal(c.lean_cycle_h)}</td>
                  <td className="num">{formatPercent(c.value_added_pct)}</td>
                  <td className="num">{formatPercent(c.waste_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export function NotesPanel({ data }: { data: DashboardResponse }) {
  return (
    <div className="two-cols">
      <Card title="Hallazgos" id="findings">
        <p className="muted small">
          Generados a partir de los resultados calculados; son orientativos y no establecen causas.
        </p>
        <ul>
          {data.findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      </Card>
      <Card title="Advertencias y supuestos" id="warnings">
        {data.warnings.length === 0 ? (
          <EmptyState title="Sin advertencias" />
        ) : (
          <ul>
            {data.warnings.map((warning) => (
              <li key={warning}>
                <span aria-hidden="true">⚠</span> {warning}
              </li>
            ))}
          </ul>
        )}
        <p>
          <strong>Pronóstico de demanda con ML:</strong>{' '}
          {data.ml_forecast_available ? 'disponible (ver el panel inferior)' : NOT_AVAILABLE}
        </p>
      </Card>
    </div>
  )
}

/** ML frente al percentil histórico: pronóstico del siguiente día por corredor. */
export function MlForecastPanel({ data }: { data: DashboardResponse }) {
  if (!data.ml_forecast_available || data.ml_forecast.length === 0) return null
  const designByCorridor = new Map(data.corridors.map((c) => [c.code, c.design_t]))
  const day = data.ml_forecast[0]?.day
  return (
    <Card title="Pronóstico de demanda con ML frente al percentil histórico" id="ml-forecast">
      <p className="muted small">
        Pronóstico para el {day} con datos sintéticos de demostración. El P90 del modelo y el
        percentil histórico responden la misma pregunta con métodos distintos; el pronóstico no
        reemplaza la demanda de diseño del balance (que sigue usando el percentil).
      </p>
      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Pronóstico ML frente al percentil histórico</caption>
          <thead>
            <tr>
              <th scope="col">Corredor</th>
              <th scope="col" className="num">P50 ML (t)</th>
              <th scope="col" className="num">P90 ML (t)</th>
              <th scope="col" className="num">Línea base ingenua (t)</th>
              <th scope="col" className="num">P90 histórico de ML (t)</th>
              <th scope="col" className="num">Demanda de diseño del balance (t)</th>
            </tr>
          </thead>
          <tbody>
            {data.ml_forecast.map((f) => (
              <tr key={f.corridor_code}>
                <th scope="row">
                  {f.corridor_code}
                  <div className="muted small">{f.corridor_name}</div>
                </th>
                <td className="num">{formatDecimal(f.p50_t)}</td>
                <td className="num">{formatDecimal(f.p90_t)}</td>
                <td className="num">{f.baseline_t === null ? NOT_AVAILABLE : formatDecimal(f.baseline_t)}</td>
                <td className="num">{formatDecimal(f.historical_p90_t)}</td>
                <td className="num">{formatDecimal(designByCorridor.get(f.corridor_code))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
