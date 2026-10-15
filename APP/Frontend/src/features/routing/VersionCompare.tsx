import { useState } from 'react'

import { ApiError } from '../../api/errors'
import type { PlanDetailOut, PlanSummaryOut } from '../../api/types'
import { Badge, LoadingState } from '../../components/common'
import { formatDateTime, formatInt } from '../../domain-ui/format'
import { diffSequences } from '../../domain-ui/planDiff'
import { formatMinutes } from '../../domain-ui/routing'
import { useAuth } from '../auth/AuthProvider'

const orderIds = (d: PlanDetailOut, vehicleId: string): string[] =>
  (d.routes.find((r) => r.vehicle_id === vehicleId)?.stops ?? []).map((s) => s.order_id ?? s.label)

/** Compara dos versiones del plan: métricas y cómo cambió la secuencia de cada vehículo. */
export function VersionCompare({ versions }: { versions: PlanSummaryOut[] }) {
  const { client } = useAuth()
  const [a, setA] = useState(versions[0]?.version ?? 1)
  const [b, setB] = useState(versions[versions.length - 1]?.version ?? 1)
  const [state, setState] = useState<
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'error'; message: string }
    | { status: 'ready'; left: PlanDetailOut; right: PlanDetailOut }
  >({ status: 'idle' })

  if (versions.length < 2) {
    return (
      <p className="muted">
        Todavía hay una sola versión del plan. Cada re-ruteo aprobado crea una nueva y aquí podrá
        compararlas.
      </p>
    )
  }

  const compare = async () => {
    setState({ status: 'loading' })
    try {
      const [left, right] = await Promise.all([client.planVersion(a), client.planVersion(b)])
      setState({ status: 'ready', left, right })
    } catch (error) {
      setState({
        status: 'error',
        message: error instanceof ApiError ? error.message : 'No se pudo cargar la comparación.',
      })
    }
  }

  const vehicleIds =
    state.status === 'ready'
      ? [...new Set([...state.left.routes, ...state.right.routes].map((r) => r.vehicle_id))]
      : []

  return (
    <div>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="cmp-a">Versión base</label>
          <select id="cmp-a" value={a} onChange={(e) => setA(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                Versión {v.version} · {v.reason}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="cmp-b">Versión a comparar</label>
          <select id="cmp-b" value={b} onChange={(e) => setB(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                Versión {v.version} · {v.reason}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn" onClick={() => void compare()}>
          Comparar
        </button>
      </div>

      {state.status === 'loading' ? <LoadingState label="Cargando versiones…" /> : null}
      {state.status === 'error' ? (
        <div className="alert alert-error" role="alert">
          {state.message}
        </div>
      ) : null}
      {state.status === 'ready' ? (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Comparación de dos versiones del plan</caption>
            <thead>
              <tr>
                <th scope="col">Indicador</th>
                <th scope="col">Versión {state.left.summary.version}</th>
                <th scope="col">Versión {state.right.summary.version}</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ['Creada', (s: PlanSummaryOut) => formatDateTime(s.created_at)],
                  ['Motivo', (s: PlanSummaryOut) => s.reason],
                  ['Responsable', (s: PlanSummaryOut) => s.created_by],
                  ['Puntaje (menor es mejor)', (s: PlanSummaryOut) => formatInt(s.score)],
                  ['Entregas tarde', (s: PlanSummaryOut) => formatInt(s.late_stops)],
                  ['Retraso proyectado', (s: PlanSummaryOut) => formatMinutes(s.delay_min)],
                  ['Vehículos en operación', (s: PlanSummaryOut) => formatInt(s.vehicles_in_use)],
                  ['Pedidos sin asignar', (s: PlanSummaryOut) => formatInt(s.unassigned)],
                ] as const
              ).map(([label, pick]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td>{pick(state.left.summary)}</td>
                  <td>{pick(state.right.summary)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Secuencia por vehículo</h3>
          {vehicleIds.map((vid) => {
            const left = orderIds(state.left, vid)
            const right = orderIds(state.right, vid)
            const plate =
              state.right.routes.find((r) => r.vehicle_id === vid)?.plate ??
              state.left.routes.find((r) => r.vehicle_id === vid)?.plate ??
              vid
            const diff = diffSequences(left, right)
            const changed = diff.some((d) => d.change !== 'same')
            return (
              <div key={vid} className="seq-row">
                <strong>{plate}</strong>{' '}
                {changed ? <Badge tone="warn">Cambió</Badge> : <Badge tone="neutral">Igual</Badge>}
                <ol className="seq">
                  {diff.map((d) => (
                    <li key={`${d.item}-${d.change}`} className={`seq-${d.change}`}>
                      {d.item}
                      {d.change === 'new' ? ' (nueva)' : d.change === 'moved' ? ' (cambió de lugar)' : ''}
                      {d.change === 'removed' ? ' (ya no está)' : ''}
                    </li>
                  ))}
                </ol>
              </div>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
