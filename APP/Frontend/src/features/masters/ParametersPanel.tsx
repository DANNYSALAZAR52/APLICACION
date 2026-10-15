import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError } from '../../api/errors'
import type { ParameterOut } from '../../api/types'
import { Badge, Card, ErrorState, LoadingState } from '../../components/common'
import { formatField } from '../../domain-ui/masters'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'

const AREAS = { capacidad: 'Capacidad de flota', ruteo: 'Ruteo diario' } as const

function ChangeDialog({
  parameter,
  onDone,
  onCancel,
}: {
  parameter: ParameterOut
  onDone: (text: string) => void
  onCancel: () => void
}) {
  const { client } = useAuth()
  const field = parameter.field
  const [value, setValue] = useState(String(parameter.value))
  const [validFrom, setValidFrom] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const today = new Date().toISOString().slice(0, 10)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!value.trim()) {
      setError('Escriba el nuevo valor.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await client.setParameter(parameter.key, value.trim(), validFrom || undefined, note.trim() || undefined)
      onDone(
        validFrom && validFrom > today
          ? `Parámetro programado: aplicará desde el ${validFrom}.`
          : 'Parámetro actualizado. El valor anterior queda en el historial.',
      )
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo guardar el parámetro.')
      setBusy(false)
    }
  }

  return (
    <div className="dialog-backdrop">
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="param-title" onSubmit={(e) => void submit(e)} noValidate>
        <h2 id="param-title">Cambiar: {parameter.label}</h2>
        {parameter.help ? <p className="muted small">{parameter.help}</p> : null}
        {error ? (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="param-value">
            Nuevo valor{field.unit ? ` (${field.unit})` : ''}
          </label>
          <input
            id="param-value"
            value={value}
            inputMode={field.type === 'time' ? undefined : 'decimal'}
            placeholder={field.type === 'time' ? 'HH:MM' : undefined}
            onChange={(e) => setValue(e.target.value)}
            autoComplete="off"
          />
          <span className="muted small">
            Rango: {field.min ?? '—'} a {field.max ?? '—'}
          </span>
        </div>
        <div className="field">
          <label htmlFor="param-from">Vigente desde (opcional)</label>
          <input id="param-from" type="date" min={today} value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          <span className="muted small">Vacío = desde hoy. No se puede fijar una fecha pasada.</span>
        </div>
        <div className="field">
          <label htmlFor="param-note">Motivo (opcional)</label>
          <input id="param-note" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" disabled={busy} onClick={onCancel}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </form>
    </div>
  )
}

/** Parámetros con vigencia: cada cambio crea una versión y conserva la anterior. */
export function ParametersPanel({ onChanged }: { onChanged: () => void }) {
  const { client } = useAuth()
  const { state, reload } = useApiResource((signal) => client.masterParameters(signal))
  const [changing, setChanging] = useState<ParameterOut | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  if (state.status === 'loading') return <LoadingState label="Cargando parámetros…" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={reload} />

  return (
    <div>
      <p className="muted">
        Los de capacidad aplican en la siguiente consulta del tablero; los de ruteo, al reiniciar el
        día operativo. Los cambios con fecha futura se programan y no se usan antes.
      </p>
      {message ? (
        <div className="alert alert-ok" role="status">
          {message}{' '}
          <button type="button" className="btn btn-small" onClick={() => setMessage(null)}>
            Entendido
          </button>
        </div>
      ) : null}
      {(Object.keys(AREAS) as (keyof typeof AREAS)[]).map((area) => (
        <Card key={area} title={AREAS[area]} id={`params-${area}`}>
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Parámetros de {AREAS[area]}</caption>
              <thead>
                <tr>
                  <th scope="col">Parámetro</th>
                  <th scope="col">Valor vigente</th>
                  <th scope="col">Vigente desde</th>
                  <th scope="col">Versiones</th>
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {state.data
                  .filter((p) => p.area === area)
                  .map((p) => (
                    <tr key={p.key}>
                      <th scope="row">
                        {p.label}
                        {p.help ? <div className="muted small">{p.help}</div> : null}
                      </th>
                      <td>{formatField(p.field, p.value)}</td>
                      <td>{p.valid_from <= '2000-01-01' ? 'Valor inicial' : p.valid_from}</td>
                      <td>
                        <details>
                          <summary>{p.versions.length} versión(es)</summary>
                          <ul className="plain small">
                            {p.versions.map((v) => (
                              <li key={`${v.valid_from}-${v.set_at}`}>
                                {formatField(p.field, v.value)} · desde {v.valid_from <= '2000-01-01' ? 'el inicio' : v.valid_from} · {v.set_by}
                                {v.in_force ? ' ' : ''}
                                {v.in_force ? <Badge tone="ok">Vigente</Badge> : null}
                                {v.scheduled ? <Badge tone="warn">Programada</Badge> : null}
                                {v.note ? ` · ${v.note}` : ''}
                              </li>
                            ))}
                          </ul>
                        </details>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-small"
                          aria-label={`Cambiar ${p.label}`}
                          onClick={() => setChanging(p)}
                        >
                          Cambiar
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
      {changing ? (
        <ChangeDialog
          parameter={changing}
          onCancel={() => setChanging(null)}
          onDone={(text) => {
            setChanging(null)
            setMessage(text)
            reload()
            onChanged()
          }}
        />
      ) : null}
    </div>
  )
}
