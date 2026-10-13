import { useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DashboardResponse } from '../../api/types'
import { Badge, Card, EmptyState } from '../../components/common'
import { formatInt, scenarioLabel, vehicleLabel } from '../../domain-ui/format'

const COLORS = ['#1d4ed8', '#15803d', '#b45309', '#7e22ce']

export function ProjectionPanel({ data }: { data: DashboardResponse }) {
  const scenarios = data.projections
  const [selected, setSelected] = useState(scenarios[0]?.scenario ?? '')
  if (scenarios.length === 0) {
    return (
      <Card title="Proyección a cinco años" id="projection">
        <EmptyState title="No hay escenarios configurados" />
      </Card>
    )
  }

  const years = scenarios[0]?.years.map((y) => y.year) ?? []
  const chartData = years.map((year) => ({
    year,
    ...Object.fromEntries(
      scenarios.map((s) => [
        scenarioLabel(s.scenario),
        s.years.find((y) => y.year === year)?.total_required ?? null,
      ]),
    ),
  }))
  const current = scenarios.find((s) => s.scenario === selected) ?? scenarios[0]
  const types = data.vehicle_types

  return (
    <Card title="Proyección a cinco años" id="projection">
      <p className="muted small">
        Flota requerida total por escenario (año base {data.base_year}). La línea punteada es la flota
        actual ({formatInt(data.totals.current)}).
      </p>
      <div className="chart" role="img" aria-label="Gráfico de líneas de la flota requerida por escenario; los datos están en la tabla inferior.">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" />
            <YAxis allowDecimals={false} domain={['auto', 'auto']} />
            <Tooltip />
            <Legend />
            <ReferenceLine
              y={data.totals.current}
              stroke="#475569"
              strokeDasharray="6 4"
              label={{ value: 'Flota actual', position: 'insideTopLeft', fill: '#475569' }}
            />
            {scenarios.map((s, index) => (
              <Line
                key={s.scenario}
                type="monotone"
                dataKey={scenarioLabel(s.scenario)}
                stroke={COLORS[index % COLORS.length]}
                strokeWidth={2}
                dot
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <ul className="deficit-list">
        {scenarios.map((s) => (
          <li key={s.scenario}>
            <strong>{scenarioLabel(s.scenario)}:</strong>{' '}
            {s.first_deficit_year === null ? (
              <Badge tone="ok">La flota actual alcanza en todo el horizonte</Badge>
            ) : (
              <Badge tone="warn">La flota actual deja de alcanzar en {s.first_deficit_year}</Badge>
            )}
          </li>
        ))}
      </ul>

      <div className="field inline">
        <label htmlFor="scenario">Escenario del detalle</label>
        <select id="scenario" value={selected} onChange={(e) => setSelected(e.target.value)}>
          {scenarios.map((s) => (
            <option key={s.scenario} value={s.scenario}>
              {scenarioLabel(s.scenario)}
            </option>
          ))}
        </select>
      </div>
      {current ? (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">
              Flota requerida por año y tipo, escenario {scenarioLabel(current.scenario)}
            </caption>
            <thead>
              <tr>
                <th scope="col">Año</th>
                {types.map((t) => (
                  <th key={t} scope="col" className="num">
                    {vehicleLabel(t)}
                  </th>
                ))}
                <th scope="col" className="num">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {current.years.map((y) => (
                <tr key={y.year}>
                  <th scope="row">{y.year}</th>
                  {types.map((t) => (
                    <td key={t} className="num">
                      {formatInt(y.required_by_type[t] ?? 0)}
                    </td>
                  ))}
                  <td className="num">
                    <strong>{formatInt(y.total_required)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  )
}
