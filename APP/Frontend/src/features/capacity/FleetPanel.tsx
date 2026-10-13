import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { DashboardResponse } from '../../api/types'
import { Card } from '../../components/common'
import { NOT_AVAILABLE, describeGap, formatInt, vehicleLabel } from '../../domain-ui/format'

export const SERIES = {
  current: { label: 'Flota actual', color: '#475569' },
  balance: { label: 'Balance', color: '#1d4ed8' },
  lean: { label: 'Lean', color: '#15803d' },
  monte_carlo_p95: { label: 'Monte Carlo P95', color: '#b45309' },
  mix: { label: 'Mix óptimo', color: '#7e22ce' },
  own_vs_third: { label: 'Propio vs tercero', color: '#0e7490' },
} as const

type SeriesKey = keyof typeof SERIES
const KEYS = Object.keys(SERIES) as SeriesKey[]

export function FleetPanel({ data }: { data: DashboardResponse }) {
  const rows = [...data.fleet, data.totals]
  const chartData = data.fleet.map((row) => ({
    tipo: vehicleLabel(row.vehicle_type),
    ...Object.fromEntries(KEYS.map((key) => [SERIES[key].label, row[key]])),
  }))

  return (
    <Card title="Flota por método y tipo de vehículo" id="fleet">
      <div className="chart" role="img" aria-label="Gráfico de barras de la flota por método y tipo; los mismos datos están en la tabla inferior.">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="tipo" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            {KEYS.map((key) => (
              <Bar key={key} dataKey={SERIES[key].label} fill={SERIES[key].color} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Flota requerida por método y tipo de vehículo</caption>
          <thead>
            <tr>
              <th scope="col">Tipo</th>
              {KEYS.map((key) => (
                <th key={key} scope="col" className="num">
                  {SERIES[key].label}
                </th>
              ))}
              <th scope="col">Brecha (actual − balance)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const gap = describeGap(row.gap)
              const total = row.vehicle_type === 'TOTAL'
              return (
                <tr key={row.vehicle_type} className={total ? 'row-total' : undefined}>
                  <th scope="row">{vehicleLabel(row.vehicle_type)}</th>
                  {KEYS.map((key) => (
                    <td key={key} className="num">
                      {row[key] === null ? NOT_AVAILABLE : formatInt(row[key])}
                    </td>
                  ))}
                  <td>
                    <span className={`gap gap-${gap.kind}`}>
                      <span aria-hidden="true">
                        {gap.kind === 'deficit' ? '⚠' : gap.kind === 'surplus' ? '✔' : '•'}
                      </span>{' '}
                      {gap.label}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
