import type { ReactNode } from 'react'

import type { DashboardResponse } from '../../api/types'
import { Badge } from '../../components/common'
import {
  NOT_AVAILABLE,
  describeGap,
  formatDecimal,
  formatInt,
  formatMoney,
  formatPercent,
  formatPercentPoints,
  solverStatusLabel,
} from '../../domain-ui/format'

function Stat({
  label,
  value,
  children,
}: {
  label: string
  value: string
  children?: ReactNode
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {children ? <div className="stat-note">{children}</div> : null}
    </div>
  )
}

export function KpiPanel({ data }: { data: DashboardResponse }) {
  const { totals, monte_carlo: mc, mix, kpis } = data
  const gap = describeGap(totals.gap)
  const saving = totals.lean === null ? null : totals.balance - totals.lean
  const gapTone = gap.kind === 'deficit' ? 'bad' : gap.kind === 'surplus' ? 'ok' : 'neutral'

  return (
    <section aria-label="Indicadores principales">
      <div className="stats">
        <Stat label="Flota actual" value={formatInt(totals.current)} />
        <Stat label="Requerida (balance)" value={formatInt(totals.balance)}>
          <Badge tone={gapTone}>{gap.label}</Badge>
        </Stat>
        <Stat label="Flota Lean" value={formatInt(totals.lean)}>
          {saving !== null && saving > 0 ? `${formatInt(saving)} menos que el balance` : null}
        </Stat>
        <Stat label="Monte Carlo (P95)" value={formatInt(mc.p95_total)}>
          La flota actual cubre el {formatDecimal(mc.coverage_pct)} % de los {formatInt(mc.days)} días
          simulados
        </Stat>
        <Stat label="Mix óptimo" value={mix.total_vehicles ? formatInt(mix.total_vehicles) : NOT_AVAILABLE}>
          <Badge tone={mix.optimal ? 'ok' : 'warn'}>{solverStatusLabel(mix.status)}</Badge>
        </Stat>
        <Stat label="Flota propia óptima" value={formatInt(totals.own_vs_third)}>
          {totals.own_vs_third === null ? 'Sin días completos de historial' : 'Propia vs. tercero'}
        </Stat>
      </div>

      <dl className="kpi-list">
        <div>
          <dt>Utilización de flota</dt>
          <dd>{formatPercent(kpis.fleet_utilization)}</dd>
        </div>
        <div>
          <dt>OEE</dt>
          <dd>{formatPercent(kpis.oee)}</dd>
        </div>
        <div>
          <dt>Llenado promedio</dt>
          <dd>{formatPercent(kpis.fill_pct)}</dd>
        </div>
        <div>
          <dt>Km en vacío</dt>
          <dd>{formatPercent(kpis.empty_km_pct)}</dd>
        </div>
        <div>
          <dt>Costo diario estimado</dt>
          <dd>{formatMoney(kpis.daily_cost)}</dd>
        </div>
        <div>
          <dt>Costo por tonelada</dt>
          <dd>{formatMoney(kpis.cost_per_ton)}</dd>
        </div>
        <div>
          <dt>Costo por tonelada-km</dt>
          <dd>{formatMoney(kpis.cost_per_ton_km)}</dd>
        </div>
        <div>
          <dt>OTIF</dt>
          <dd>
            {kpis.otif === null ? (
              <span title="Se calcula con las entregas del módulo de ruteo">
                {NOT_AVAILABLE} (requiere ruteo)
              </span>
            ) : (
              formatPercentPoints(kpis.otif * 100)
            )}
          </dd>
        </div>
      </dl>
    </section>
  )
}
