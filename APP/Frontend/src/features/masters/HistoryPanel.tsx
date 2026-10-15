import { useState } from 'react'

import type { MasterSchema } from '../../api/types'
import { Card, EmptyState, ErrorState, LoadingState } from '../../components/common'
import { formatDateTime } from '../../domain-ui/format'
import { ACTION_LABELS, changedFields } from '../../domain-ui/masters'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'

const show = (v: unknown): string => (v === null || v === undefined ? '—' : String(v))

function HistoryTable({ entity, schema }: { entity: string; schema: MasterSchema }) {
  const { client } = useAuth()
  const { state, reload } = useApiResource((signal) => client.masterHistory(entity || undefined, signal))
  const label = (name: string) =>
    name === 'parameter' ? 'Parámetro' : (schema.entities.find((e) => e.name === name)?.label ?? name)

  if (state.status === 'loading') return <LoadingState label="Cargando historial…" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={reload} />
  if (state.data.length === 0) {
    return <EmptyState title="Sin cambios registrados">Los cambios que haga aparecerán aquí.</EmptyState>
  }
  return (
    <div className="table-wrap">
      <table>
        <caption className="visually-hidden">Historial de cambios de maestros y parámetros</caption>
        <thead>
          <tr>
            <th scope="col">Cuándo</th>
            <th scope="col">Quién</th>
            <th scope="col">Qué</th>
            <th scope="col">Cambio (antes → después)</th>
            <th scope="col">Vigencia</th>
          </tr>
        </thead>
        <tbody>
          {state.data.map((c) => (
            <tr key={c.id}>
              <td>{formatDateTime(c.at)}</td>
              <td>{c.actor}</td>
              <td>
                {ACTION_LABELS[c.action]} · {label(c.entity)} <strong>{c.key}</strong>
              </td>
              <td>
                {c.action === 'delete' ? (
                  <span className="muted">Registro eliminado</span>
                ) : c.action === 'create' ? (
                  <span className="muted">Registro nuevo</span>
                ) : (
                  changedFields(c.before, c.after).map((f) => (
                    <div key={f.name}>
                      {f.name}: {show(f.before)} → <strong>{show(f.after)}</strong>
                    </div>
                  ))
                )}
                {c.note ? <div className="muted small">{c.note}</div> : null}
              </td>
              <td>{c.valid_from ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Historial de cambios: quién, cuándo, qué cambió y el valor anterior. */
export function HistoryPanel({ schema, refreshKey }: { schema: MasterSchema; refreshKey: number }) {
  const [entity, setEntity] = useState('')
  return (
    <Card title="Historial de cambios" id="history">
      <div className="field inline">
        <label htmlFor="history-entity">Filtrar por</label>
        <select id="history-entity" value={entity} onChange={(e) => setEntity(e.target.value)}>
          <option value="">Todo</option>
          <option value="parameter">Parámetros</option>
          {schema.entities.map((e) => (
            <option key={e.name} value={e.name}>
              {e.plural}
            </option>
          ))}
        </select>
      </div>
      <HistoryTable key={`${entity}-${refreshKey}`} entity={entity} schema={schema} />
    </Card>
  )
}
