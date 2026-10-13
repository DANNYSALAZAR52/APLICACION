import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DashboardResponse } from '../../api/types'
import { Badge, Card, EmptyState } from '../../components/common'
import { formatInt, formatMoney, solverStatusLabel, vehicleLabel } from '../../domain-ui/format'

export function MixPanel({ data }: { data: DashboardResponse }) {
  const { mix } = data
  return (
    <Card title="Optimización del mix de flota" id="mix">
      <p>
        Estado del optimizador:{' '}
        <Badge tone={mix.optimal ? 'ok' : 'warn'}>{solverStatusLabel(mix.status)}</Badge>
      </p>
      {mix.message ? <p className="muted">{mix.message}</p> : null}
      {mix.assignments.length === 0 ? (
        <EmptyState title="Sin solución utilizable">
          El optimizador no entregó una asignación; se informa su estado real en lugar de un resultado
          incompleto.
        </EmptyState>
      ) : (
        <>
          <p>
            Costo diario del mix: <strong>{formatMoney(mix.total_cost_per_day)}</strong> ·{' '}
            {formatInt(mix.total_vehicles)} vehículos.
          </p>
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Vehículos asignados por corredor y tipo</caption>
              <thead>
                <tr>
                  <th scope="col">Corredor</th>
                  <th scope="col">Tipo de vehículo</th>
                  <th scope="col" className="num">
                    Vehículos
                  </th>
                </tr>
              </thead>
              <tbody>
                {mix.assignments.map((a) => (
                  <tr key={`${a.corridor}-${a.vehicle_type}`}>
                    <th scope="row">{a.corridor}</th>
                    <td>{vehicleLabel(a.vehicle_type)}</td>
                    <td className="num">{formatInt(a.count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  )
}

export function OwnVsThirdPanel({ data }: { data: DashboardResponse }) {
  const items = data.own_vs_third
  const [selected, setSelected] = useState(items[0]?.vehicle_type ?? '')
  if (items.length === 0) {
    return (
      <Card title="Flota propia vs. terceros" id="own-vs-third">
        <EmptyState title="Sin datos suficientes">
          No hay días con demanda registrada en todos los corredores; no se completan con ceros.
        </EmptyState>
      </Card>
    )
  }
  const item = items.find((i) => i.vehicle_type === selected) ?? items[0]
  if (!item) return null
  const optimum = item.curve.find((p) => p.own_fleet === item.optimal_own)
  const savingVsThird = item.all_third_party_cost_per_day - item.optimal_cost_per_day

  return (
    <Card title="Flota propia vs. terceros" id="own-vs-third">
      <div className="field inline">
        <label htmlFor="own-type">Tipo de vehículo</label>
        <select id="own-type" value={item.vehicle_type} onChange={(e) => setSelected(e.target.value)}>
          {items.map((i) => (
            <option key={i.vehicle_type} value={i.vehicle_type}>
              {vehicleLabel(i.vehicle_type)}
            </option>
          ))}
        </select>
      </div>
      <p>
        Con {formatInt(item.days_used)} días de historial completos, la flota propia de menor costo
        es de <strong>{formatInt(item.optimal_own)} vehículos</strong> (
        {formatMoney(item.optimal_cost_per_day)} por día).
      </p>
      <ul className="plain">
        <li>Todo con terceros: {formatMoney(item.all_third_party_cost_per_day)} por día</li>
        <li>Todo propio: {formatMoney(item.all_own_cost_per_day)} por día</li>
        <li>
          Ahorro frente a todo terceros: <strong>{formatMoney(Math.max(savingVsThird, 0))}</strong> por día
        </li>
      </ul>
      <div
        className="chart"
        role="img"
        aria-label={`Curva de costo diario según la flota propia para ${vehicleLabel(item.vehicle_type)}; el mínimo está en ${item.optimal_own} vehículos.`}
      >
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={item.curve} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="own_fleet" label={{ value: 'Vehículos propios', position: 'insideBottom', offset: -2 }} />
            <YAxis tickFormatter={(v: number) => `${Math.round(v / 1_000_000)} M`} domain={['auto', 'auto']} />
            <Tooltip formatter={(v) => formatMoney(Number(v))} labelFormatter={(l) => `${l} propios`} />
            <Line type="monotone" dataKey="daily_cost" name="Costo diario" stroke="#0e7490" strokeWidth={2} dot={false} />
            {optimum ? (
              <ReferenceDot x={optimum.own_fleet} y={optimum.daily_cost} r={6} fill="#b91c1c" stroke="#fff" />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
