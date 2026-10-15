import { useState } from 'react'

import { ApiError } from '../../api/errors'
import { ErrorState, LoadingState } from '../../components/common'
import { dashboardRows, downloadCsv, saveBlob, toCsv } from '../../domain-ui/csv'
import { formatDateTime, formatInt, formatPercent } from '../../domain-ui/format'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'
import { CorridorsPanel, MlForecastPanel, NotesPanel } from './DetailPanels'
import { FleetPanel } from './FleetPanel'
import { KpiPanel } from './KpiPanel'
import { MixPanel, OwnVsThirdPanel } from './MixAndOwnPanels'
import { ProjectionPanel } from './ProjectionPanel'

export function CapacityPage() {
  const { client, user } = useAuth()
  const { state, reload } = useApiResource((signal) => client.dashboard(signal))
  const canRecalculate = user?.permissions.includes('capacity:recalculate') ?? false
  const [exportError, setExportError] = useState<string | null>(null)

  if (state.status === 'loading') return <LoadingState label="Calculando la capacidad de flota…" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={reload} />

  const data = state.data
  const exportCsv = () =>
    downloadCsv(`capacidad-flota-${data.run_at.slice(0, 10)}.csv`, toCsv(dashboardRows(data)))

  const exportExcel = async () => {
    setExportError(null)
    try {
      const file = await client.download('/capacity/export.xlsx')
      saveBlob(file.filename, file.blob)
    } catch (e) {
      setExportError(e instanceof ApiError ? e.message : 'No se pudo generar el Excel.')
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Capacidad de flota</h1>
          <p className="muted">
            ¿Cuántos vehículos se necesitan hoy y en los próximos cinco años? Resultados de apoyo a la
            decisión: no generan compras ni contratos.
          </p>
          <p className="meta">
            <span>Calculado: {formatDateTime(data.run_at)}</span>
            <span>Algoritmo {data.algorithm_version}</span>
            <span>Percentil de diseño: P{Math.round(data.parameters.design_percentile * 100)}</span>
            <span>Reserva: {formatPercent(data.parameters.reserve)}</span>
            <span>Ventana: {formatInt(data.parameters.window_days)} días</span>
          </p>
        </div>
        <div className="actions">
          {canRecalculate ? (
            <button type="button" className="btn btn-primary" onClick={reload}>
              Recalcular
            </button>
          ) : null}
          <button type="button" className="btn" onClick={() => void exportExcel()}>
            Exportar Excel
          </button>
          <button type="button" className="btn" onClick={exportCsv}>
            Exportar CSV
          </button>
        </div>
      </div>

      {exportError ? (
        <div className="alert alert-error" role="alert">
          {exportError}
        </div>
      ) : null}

      <KpiPanel data={data} />
      <FleetPanel data={data} />
      <ProjectionPanel data={data} />
      <div className="two-cols">
        <MixPanel data={data} />
        <OwnVsThirdPanel data={data} />
      </div>
      <CorridorsPanel data={data} />
      <MlForecastPanel data={data} />
      <NotesPanel data={data} />
    </div>
  )
}
