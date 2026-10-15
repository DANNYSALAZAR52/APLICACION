import { useState } from 'react'

import { ApiError } from '../../api/errors'
import type { EntitySpec, MasterRow, MasterSchema } from '../../api/types'
import { Card, ConfirmDialog, EmptyState, ErrorState, LoadingState } from '../../components/common'
import { saveBlob } from '../../domain-ui/csv'
import { formatField, keyOf } from '../../domain-ui/masters'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'
import { CsvDialog } from './CsvDialog'
import { EntityForm } from './EntityForm'

interface Props {
  entity: EntitySpec
  schema: MasterSchema
  /** Se llama tras cualquier cambio para refrescar listas de otros maestros. */
  onChanged: () => void
}

/** Tabla, alta/edición/baja, carga CSV y exportación de UN maestro. */
export function EntityPanel({ entity, schema, onChanged }: Props) {
  const { client } = useAuth()
  const { state, reload } = useApiResource((signal) => client.masterRows(entity.name, signal))
  const [editing, setEditing] = useState<{ row: MasterRow | null } | null>(null)
  const [deleting, setDeleting] = useState<MasterRow | null>(null)
  const [csvOpen, setCsvOpen] = useState(false)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const changed = (text: string) => {
    setMessage({ tone: 'ok', text })
    reload()
    onChanged()
  }

  const save = async (values: Record<string, unknown>) => {
    const row = editing?.row ?? null
    if (row) await client.masterUpdate(entity.name, keyOf(row, entity.key_fields), values)
    else await client.masterCreate(entity.name, values)
    setEditing(null)
    changed(row ? 'Cambios guardados.' : `${entity.label} creado.`)
  }

  const remove = async () => {
    if (!deleting) return
    setBusy(true)
    try {
      await client.masterDelete(entity.name, keyOf(deleting, entity.key_fields))
      setDeleting(null)
      changed('Registro eliminado.')
    } catch (e) {
      setDeleting(null)
      setMessage({ tone: 'error', text: e instanceof ApiError ? e.message : 'No se pudo eliminar.' })
    } finally {
      setBusy(false)
    }
  }

  const download = async (format: 'csv' | 'xlsx') => {
    setBusy(true)
    try {
      const file = await client.download(`/masters/entities/${entity.name}/export?format=${format}`)
      saveBlob(file.filename, file.blob)
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof ApiError ? e.message : 'No se pudo exportar.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title={entity.plural} id={`entity-${entity.name}`}>
      <p className="muted">{entity.description}</p>
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={() => setEditing({ row: null })}>
          Nuevo
        </button>
        {entity.csv ? (
          <button type="button" className="btn" onClick={() => setCsvOpen(true)}>
            Cargar CSV
          </button>
        ) : null}
        <button type="button" className="btn" disabled={busy} onClick={() => void download('csv')}>
          Exportar CSV
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => void download('xlsx')}>
          Exportar Excel
        </button>
      </div>
      {message ? (
        <div className={`alert ${message.tone === 'ok' ? 'alert-ok' : 'alert-error'}`} role={message.tone === 'ok' ? 'status' : 'alert'}>
          {message.text}{' '}
          <button type="button" className="btn btn-small" onClick={() => setMessage(null)}>
            Cerrar
          </button>
        </div>
      ) : null}

      {state.status === 'loading' ? <LoadingState label={`Cargando ${entity.plural.toLowerCase()}…`} /> : null}
      {state.status === 'error' ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === 'success' && state.data.rows.length === 0 ? (
        <EmptyState title="Sin registros">Use «Nuevo» o «Cargar CSV» para agregar.</EmptyState>
      ) : null}
      {state.status === 'success' && state.data.rows.length > 0 ? (
        <>
          <p className="muted small">
            {state.data.total} registro(s)
            {state.data.truncated ? ` · se muestran los ${state.data.rows.length} más recientes` : ''}
          </p>
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">{entity.plural}</caption>
              <thead>
                <tr>
                  {entity.fields.map((f) => (
                    <th key={f.name} scope="col" className={['int', 'number', 'percent'].includes(f.type) ? 'num' : undefined}>
                      {f.label}
                    </th>
                  ))}
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {state.data.rows.map((row) => {
                  const key = keyOf(row, entity.key_fields)
                  return (
                    <tr key={key}>
                      {entity.fields.map((f) => (
                        <td key={f.name} className={['int', 'number', 'percent'].includes(f.type) ? 'num' : undefined}>
                          {formatField(f, row[f.name], schema.lookups)}
                        </td>
                      ))}
                      <td className="row-actions">
                        <button
                          type="button"
                          className="btn btn-small"
                          aria-label={`Editar ${key}`}
                          onClick={() => setEditing({ row })}
                        >
                          Editar
                        </button>{' '}
                        <button
                          type="button"
                          className="btn btn-small"
                          aria-label={`Eliminar ${key}`}
                          onClick={() => setDeleting(row)}
                        >
                          Eliminar
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {editing ? (
        <EntityForm
          entity={entity}
          lookups={schema.lookups}
          row={editing.row}
          onSubmit={save}
          onCancel={() => setEditing(null)}
        />
      ) : null}
      {csvOpen ? (
        <CsvDialog
          entity={entity}
          onCancel={() => setCsvOpen(false)}
          onDone={(text) => {
            setCsvOpen(false)
            changed(text)
          }}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          title="Eliminar registro"
          confirmLabel="Eliminar"
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setDeleting(null)}
        >
          <p>
            ¿Eliminar <strong>{keyOf(deleting, entity.key_fields)}</strong>? El cambio queda en el historial con su
            valor anterior. Si otro maestro lo usa, no se podrá eliminar.
          </p>
        </ConfirmDialog>
      ) : null}
    </Card>
  )
}
