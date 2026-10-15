import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ApiError } from '../../api/errors'
import type { CorridorForecastOut, ModelOut, PatternsOut } from '../../api/types'
import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../../components/common'
import { formatDateTime, formatDecimal, formatInt, formatPercent } from '../../domain-ui/format'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'

// Colores validados para daltonismo (azul y naranja); además cada serie se distingue por trazo.
const ACTUAL = '#0072B2'
const FORECAST = '#D55E00'

const WEEKDAYS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
const shortDay = (iso: string): string => {
  const [, month, day] = iso.split('-')
  return `${day}/${month}`
}

function Provenance({ data }: { data: PatternsOut }) {
  return (
    <div className="notice" role="note">
      <Badge tone="warn">Datos sintéticos</Badge> {data.provenance}
    </div>
  )
}

function ForecastCard({ corridors }: { corridors: CorridorForecastOut[] }) {
  const [selected, setSelected] = useState(corridors[0]?.corridor_code ?? '')
  const corridor = corridors.find((c) => c.corridor_code === selected) ?? corridors[0]
  const rows = useMemo(() => {
    if (!corridor) return []
    return [
      ...corridor.recent.map((r) => ({ day: r.day, label: shortDay(r.day), actual: r.tons })),
      ...corridor.forecast.map((f) => ({
        day: f.day,
        label: shortDay(f.day),
        p50: f.p50_t,
        p90: f.p90_t,
      })),
    ]
  }, [corridor])

  if (!corridor) {
    return (
      <Card title="Pronóstico de demanda por corredor" id="forecast">
        <EmptyState title="Sin corredores con historia suficiente" />
      </Card>
    )
  }
  return (
    <Card title="Pronóstico de demanda por corredor" id="forecast">
      <p className="muted small">
        Toneladas por día: demanda observada (últimos 28 días) y pronóstico de los próximos 7 días
        con su intervalo (P50 = valor central; P90 = valor que debería superarse solo 1 de cada 10
        días).
      </p>
      <div className="field inline">
        <label htmlFor="forecast-corridor">Corredor</label>
        <select
          id="forecast-corridor"
          value={corridor.corridor_code}
          onChange={(e) => setSelected(e.target.value)}
        >
          {corridors.map((c) => (
            <option key={c.corridor_code} value={c.corridor_code}>
              {c.corridor_code} · {c.corridor_name}
            </option>
          ))}
        </select>
      </div>
      <div
        className="chart"
        role="img"
        aria-label={`Demanda diaria observada y pronóstico del corredor ${corridor.corridor_name}; los datos están en la tabla inferior.`}
      >
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={24} />
            <YAxis allowDecimals={false} unit=" t" width={56} />
            <Tooltip />
            <Legend />
            <Line
              name="Observada"
              dataKey="actual"
              stroke={ACTUAL}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
            />
            <Line
              name="Pronóstico P50"
              dataKey="p50"
              stroke={FORECAST}
              strokeWidth={2}
              dot
              connectNulls={false}
            />
            <Line
              name="Pronóstico P90"
              dataKey="p90"
              stroke={FORECAST}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        Percentil histórico P90 de los últimos 60 días:{' '}
        <strong>
          {corridor.historical_p90_t === null ? 'sin datos' : `${formatDecimal(corridor.historical_p90_t)} t`}
        </strong>
        . Línea base ingenua: el valor de hace 7 días.
      </p>
      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">
            Pronóstico de demanda del corredor {corridor.corridor_name}
          </caption>
          <thead>
            <tr>
              <th scope="col">Día</th>
              <th scope="col" className="num">P50 (t)</th>
              <th scope="col" className="num">P90 (t)</th>
              <th scope="col" className="num">Línea base (t)</th>
            </tr>
          </thead>
          <tbody>
            {corridor.forecast.map((f) => (
              <tr key={f.day}>
                <th scope="row">{f.day}</th>
                <td className="num">{formatDecimal(f.p50_t)}</td>
                <td className="num">{formatDecimal(f.p90_t)}</td>
                <td className="num">{f.baseline_t === null ? '—' : formatDecimal(f.baseline_t)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function AnomaliesCard({ data }: { data: PatternsOut }) {
  return (
    <Card title="Anomalías por cliente" id="anomalies">
      <p className="muted small">
        Ordenadas por severidad. Son asociaciones estadísticas respecto del patrón habitual de cada
        cliente: indican dónde mirar, no la causa.
      </p>
      {data.anomalies.length === 0 ? (
        <EmptyState title="No se detectaron anomalías en este conjunto de datos" />
      ) : (
        <ol className="finding-list">
          {data.anomalies.map((a) => (
            <li key={`${a.customer_code}-${a.weekday}-${a.hour_from}-${a.kind}`}>
              <Badge tone={a.severity >= 5 ? 'bad' : 'warn'}>
                Severidad {formatDecimal(a.severity, 1)}
              </Badge>{' '}
              {a.message}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

function DelayCard({ data }: { data: PatternsOut }) {
  return (
    <Card title="Riesgo de retraso por cliente" id="delay">
      <p className="muted small">
        Probabilidad estimada de llegar fuera de ventana en las condiciones típicas de cada cliente
        (su hora habitual, su carga y el tráfico de esa hora). Es una estimación, no una certeza:
        sirve para priorizar la atención.
      </p>
      {data.delay_risks.length === 0 ? (
        <EmptyState title="Sin estimaciones de riesgo" />
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Riesgo de retraso por cliente</caption>
            <thead>
              <tr>
                <th scope="col">Cliente</th>
                <th scope="col" className="num">Hora típica</th>
                <th scope="col" className="num">Factor de tráfico</th>
                <th scope="col" className="num">Paradas restantes</th>
                <th scope="col" className="num">Carga (kg)</th>
                <th scope="col" className="num">Riesgo estimado</th>
              </tr>
            </thead>
            <tbody>
              {data.delay_risks.map((r) => (
                <tr key={r.customer_code}>
                  <th scope="row">{r.customer_name}</th>
                  <td className="num">{String(r.hour).padStart(2, '0')}:00</td>
                  <td className="num">{formatDecimal(r.traffic_factor)}</td>
                  <td className="num">{formatInt(r.stops_remaining)}</td>
                  <td className="num">{formatInt(r.order_kg)}</td>
                  <td className="num">
                    <strong>{formatPercent(r.probability)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function SegmentsCard({ data }: { data: PatternsOut }) {
  return (
    <Card title="Segmentos de clientes" id="segments">
      <p className="muted small">
        Agrupación por comportamiento de servicio (tiempo, tamaño de pedido, ventana y variación
        semanal). Los nombres describen diferencias dentro de esta empresa; no son categorías
        objetivas.
      </p>
      {data.segments.length === 0 ? (
        <EmptyState title="Sin segmentos" />
      ) : (
        <div className="segment-grid">
          {data.segments.map((s) => (
            <section key={s.segment_id} className="segment" aria-label={s.name}>
              <h3>{s.name}</h3>
              <p>{s.description}</p>
              <p className="muted small">
                Variación semanal del pedido: {formatPercent(s.weekly_variation)}
              </p>
              <details>
                <summary>{formatInt(s.customers.length)} clientes</summary>
                <p className="small">{s.customers.join(', ')}</p>
              </details>
            </section>
          ))}
        </div>
      )}
    </Card>
  )
}

function ModelCard({ model }: { model: ModelOut }) {
  return (
    <section className="model" aria-label={`Modelo: ${model.title}`}>
      <h3>{model.title}</h3>
      <p className="muted small">
        Versión {model.version} · entrenado el {formatDateTime(model.trained_at)} · {model.library} ·
        semilla {model.seed} · huella SHA-256 <code>{model.artifact_sha256.slice(0, 12)}…</code>
      </p>
      <dl className="metric-list">
        {model.metrics.map((m) => (
          <div key={m.label} title={m.hint}>
            <dt>{m.label}</dt>
            <dd>{m.value}</dd>
          </div>
        ))}
      </dl>
      {model.importances.length > 0 ? (
        <>
          <p className="small">
            <strong>Variables más influyentes</strong> (importancia por permutación en la partición
            de prueba):
          </p>
          <ul className="plain small">
            {model.importances.slice(0, 5).map(([name, share]) => (
              <li key={name}>
                {name}: {formatPercent(share)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {model.notes.length > 0 ? (
        <ul className="plain muted small">
          {model.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

/** Patrones detectados (pantalla 8): pronóstico, anomalías, riesgo de retraso y segmentos. */
export function PatternsPage() {
  const { client, user } = useAuth()
  const { state, reload } = useApiResource((signal) => client.patterns(signal))
  const [retraining, setRetraining] = useState(false)
  const [retrainError, setRetrainError] = useState<string | null>(null)
  const [override, setOverride] = useState<PatternsOut | null>(null)
  const canTrain = user?.permissions.includes('patterns:train') ?? false

  const retrain = async () => {
    setRetraining(true)
    setRetrainError(null)
    try {
      setOverride(await client.retrainPatterns())
    } catch (e) {
      setRetrainError(e instanceof ApiError ? e.message : 'No se pudo reentrenar los modelos.')
    } finally {
      setRetraining(false)
    }
  }

  const data = override ?? (state.status === 'success' ? state.data : null)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Patrones detectados</h1>
          <p className="muted">
            Pronóstico de demanda, anomalías, riesgo de retraso y segmentos, con la procedencia de cada
            modelo.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn"
            onClick={() => {
              setOverride(null)
              reload()
            }}
          >
            Actualizar
          </button>
          {canTrain ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void retrain()}
              disabled={retraining}
            >
              {retraining ? 'Reentrenando…' : 'Reentrenar modelos'}
            </button>
          ) : null}
        </div>
      </div>

      {retrainError ? (
        <div className="alert alert-error" role="alert">
          {retrainError}
        </div>
      ) : null}
      {!data && state.status === 'loading' ? (
        <LoadingState label="Entrenando y evaluando los modelos (la primera vez toma unos segundos)…" />
      ) : null}
      {!data && state.status === 'error' ? (
        <ErrorState error={state.error} onRetry={reload} />
      ) : null}

      {data ? (
        <>
          <Provenance data={data} />
          <p className="muted small">
            Historia usada: {data.history_from} a {data.history_to}. Generado el{' '}
            {formatDateTime(data.generated_at)}.
          </p>
          <ForecastCard corridors={data.forecasts} />
          <div className="two-cols">
            <AnomaliesCard data={data} />
            <DelayCard data={data} />
          </div>
          <SegmentsCard data={data} />
          <Card title="Modelos y procedencia" id="models">
            <p className="muted small">
              Cada modelo se entrena solo con los datos de esta empresa, con partición temporal
              (entrenamiento antes, prueba después) y se verifica su huella antes de cargarlo.
            </p>
            <div className="model-grid">
              {data.models.map((m) => (
                <ModelCard key={m.name} model={m} />
              ))}
            </div>
          </Card>
          <Card title="Límites conocidos" id="limits">
            <ul>
              {data.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
            {data.warnings.length > 0 ? (
              <ul>
                {data.warnings.map((w) => (
                  <li key={w}>
                    <span aria-hidden="true">⚠</span> {w}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="muted small">
              Días de la semana usados en los mensajes: {WEEKDAYS.join(', ')}.
            </p>
          </Card>
        </>
      ) : null}
    </div>
  )
}
