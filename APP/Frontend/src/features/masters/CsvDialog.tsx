import { useState } from 'react'
import type { ChangeEvent } from 'react'

import { ApiError } from '../../api/errors'
import type { CsvPreview, EntitySpec } from '../../api/types'
import { Badge } from '../../components/common'
import { csvColumns } from '../../domain-ui/masters'
import { useAuth } from '../auth/AuthProvider'

const MAX_BYTES = 200_000

interface Props {
  entity: EntitySpec
  onDone: (message: string) => void
  onCancel: () => void
}

/** Carga CSV en dos pasos: previsualizar (sin tocar nada) y aplicar (todo o nada). */
export function CsvDialog({ entity, onDone, onCancel }: Props) {
  const { client } = useAuth()
  const [content, setContent] = useState('')
  const [fileName, setFileName] = useState<string | null>(null)
  const [preview, setPreview] = useState<CsvPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const choose = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    setPreview(null)
    setError(null)
    if (!file) return
    if (file.size > MAX_BYTES) {
      setError(`El archivo supera el tamaño permitido (${MAX_BYTES / 1000} KB).`)
      setContent('')
      setFileName(null)
      return
    }
    setFileName(file.name)
    setContent(await file.text())
  }

  const run = async (apply: boolean) => {
    setBusy(true)
    setError(null)
    try {
      if (apply) {
        const result = await client.csvApply(entity.name, content)
        onDone(`Carga aplicada: ${result.created} creados y ${result.updated} actualizados.`)
        return
      }
      setPreview(await client.csvPreview(entity.name, content))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo procesar el archivo.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dialog-backdrop">
      <div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="csv-title">
        <h2 id="csv-title">Cargar CSV: {entity.plural}</h2>
        <p className="muted small">
          Columnas: <code>{csvColumns(entity.fields)}</code>. Separador coma o punto y coma. Si hay
          un solo error no se aplica ninguna fila. Máximo 200 KB y 5000 filas.
        </p>
        {error ? (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="csv-file">Archivo CSV</label>
          <input id="csv-file" type="file" accept=".csv,text/csv" onChange={(e) => void choose(e)} />
          {fileName ? <span className="muted small">{fileName}</span> : null}
        </div>
        <div className="field">
          <label htmlFor="csv-text">…o pegue el contenido</label>
          <textarea
            id="csv-text"
            rows={4}
            value={content}
            onChange={(e) => {
              setContent(e.target.value)
              setPreview(null)
            }}
          />
        </div>

        {preview ? (
          <div role="region" aria-label="Resultado de la previsualización">
            <p>
              {preview.can_apply ? (
                <Badge tone="ok">Lista para aplicar</Badge>
              ) : (
                <Badge tone="bad">Tiene errores: no se puede aplicar</Badge>
              )}{' '}
              {preview.rows_total} filas · {preview.rows_valid} válidas · {preview.to_create} nuevas ·{' '}
              {preview.to_update} actualizaciones
            </p>
            {preview.errors.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <caption className="visually-hidden">Errores del archivo</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="num">Fila</th>
                      <th scope="col">Columna</th>
                      <th scope="col">Qué corregir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.errors.map((e, i) => (
                      <tr key={`${e.row}-${e.column}-${i}`}>
                        <td className="num">{e.row || '—'}</td>
                        <td>{e.column || '—'}</td>
                        <td>{e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.errors_truncated ? (
                  <p className="muted small">Se muestran los primeros errores; corrija y vuelva a previsualizar.</p>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="dialog-actions">
          <button type="button" className="btn" disabled={busy} onClick={onCancel}>
            Cerrar
          </button>
          <button type="button" className="btn" disabled={busy || !content.trim()} onClick={() => void run(false)}>
            {busy ? 'Procesando…' : 'Previsualizar'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !preview?.can_apply}
            onClick={() => void run(true)}
          >
            Aplicar carga
          </button>
        </div>
      </div>
    </div>
  )
}
