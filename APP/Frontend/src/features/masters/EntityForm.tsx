import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError } from '../../api/errors'
import type { EntitySpec, FieldSpec, MasterRow, MasterSchema } from '../../api/types'
import { optionsOf } from '../../domain-ui/masters'

type Values = Record<string, string>

const initial = (entity: EntitySpec, row: MasterRow | null): Values =>
  Object.fromEntries(
    entity.fields.map((f) => [f.name, row && row[f.name] != null ? String(row[f.name]) : '']),
  )

function FieldInput({
  field,
  value,
  lookups,
  disabled,
  invalid,
  onChange,
}: {
  field: FieldSpec
  value: string
  lookups: MasterSchema['lookups']
  disabled: boolean
  invalid: boolean
  onChange: (v: string) => void
}) {
  const id = `field-${field.name}`
  const common = {
    id,
    disabled,
    'aria-invalid': invalid ? ('true' as const) : undefined,
    'aria-describedby': field.help ? `${id}-help` : undefined,
  }
  if (field.type === 'select' || field.type === 'bool') {
    const options: [string, string][] =
      field.type === 'bool'
        ? [
            ['true', 'Sí'],
            ['false', 'No'],
          ]
        : optionsOf(field, lookups)
    return (
      <select {...common} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{field.required ? 'Elija una opción…' : '(sin valor)'}</option>
        {options.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
    )
  }
  return (
    <input
      {...common}
      type={field.type === 'date' ? 'date' : 'text'}
      inputMode={field.type === 'int' ? 'numeric' : ['number', 'percent'].includes(field.type) ? 'decimal' : undefined}
      placeholder={field.type === 'time' ? 'HH:MM' : undefined}
      maxLength={field.type === 'text' ? field.max_length : 40}
      value={value}
      autoComplete="off"
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

interface Props {
  entity: EntitySpec
  lookups: MasterSchema['lookups']
  row: MasterRow | null
  onSubmit: (values: Record<string, unknown>) => Promise<void>
  onCancel: () => void
}

/** Formulario generado desde el esquema del maestro. El backend vuelve a validar todo. */
export function EntityForm({ entity, lookups, row, onSubmit, onCancel }: Props) {
  const editing = row !== null
  const [values, setValues] = useState<Values>(() => initial(entity, row))
  const [missing, setMissing] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const empty = entity.fields.filter((f) => f.required && !values[f.name]?.trim()).map((f) => f.name)
    setMissing(new Set(empty))
    if (empty.length > 0) {
      setError('Complete los campos obligatorios marcados.')
      return
    }
    setBusy(true)
    setError(null)
    const payload: Record<string, unknown> = {}
    for (const f of entity.fields) {
      const text = values[f.name]?.trim() ?? ''
      if (text === '') continue
      payload[f.name] = f.type === 'bool' ? text === 'true' : text
    }
    try {
      await onSubmit(payload)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo guardar. Intente de nuevo.')
      setBusy(false)
    }
  }

  return (
    <div className="dialog-backdrop">
      <form
        className="dialog dialog-wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="entity-form-title"
        onSubmit={(e) => void submit(e)}
        noValidate
      >
        <h2 id="entity-form-title">
          {editing ? 'Editar' : 'Nuevo'}: {entity.label}
        </h2>
        {error ? (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        ) : null}
        <div className="form-grid">
          {entity.fields.map((f) => {
            const locked = editing && entity.key_fields.includes(f.name)
            return (
              <div className="field" key={f.name}>
                <label htmlFor={`field-${f.name}`}>
                  {f.label}
                  {f.required ? ' *' : ''}
                  {f.unit ? ` (${f.unit})` : ''}
                </label>
                <FieldInput
                  field={f}
                  value={values[f.name] ?? ''}
                  lookups={lookups}
                  disabled={locked}
                  invalid={missing.has(f.name)}
                  onChange={(v) => setValues((cur) => ({ ...cur, [f.name]: v }))}
                />
                {f.help ? (
                  <span id={`field-${f.name}-help`} className="muted small">
                    {f.help}
                  </span>
                ) : null}
                {locked ? <span className="muted small">La clave no se puede cambiar.</span> : null}
              </div>
            )
          })}
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
