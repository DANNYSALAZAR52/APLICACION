// Presentación de maestros y parámetros (sin reglas de negocio: el backend valida todo).

import type { ChangeRecord, FieldSpec, MasterRow, MasterSchema } from '../api/types'
import { formatDecimal, formatInt } from './format'

type Lookups = MasterSchema['lookups']

export const ACTION_LABELS: Record<ChangeRecord['action'], string> = {
  create: 'Creó',
  update: 'Modificó',
  delete: 'Eliminó',
  csv: 'Cargó por CSV',
  parameter: 'Cambió el parámetro',
}

/** Valor de un campo tal como se muestra en una tabla. */
export function formatField(
  field: FieldSpec,
  value: unknown,
  lookups?: Lookups,
): string {
  if (value === null || value === undefined || value === '') return '—'
  switch (field.type) {
    case 'bool':
      return value ? 'Sí' : 'No'
    case 'percent':
      return `${formatDecimal(Number(value), 1)} %`
    case 'int':
      return `${formatInt(Number(value))}${field.unit ? ` ${field.unit}` : ''}`
    case 'number': {
      const text = Number.isInteger(Number(value))
        ? formatInt(Number(value))
        : new Intl.NumberFormat('es-CO', { maximumFractionDigits: 4 }).format(Number(value))
      return field.unit ? `${text} ${field.unit}` : text
    }
    case 'select': {
      const fixed = field.options.find(([v]) => v === String(value))
      if (fixed) return fixed[1]
      if (field.options_from === 'customers') {
        const found = lookups?.customers.find(([code]) => code === String(value))
        if (found) return `${found[0]} · ${found[1]}`
      }
      if (field.options_from === 'corridors') {
        const found = lookups?.corridors.find(([code]) => code === String(value))
        if (found) return `${found[0]} · ${found[1]}`
      }
      return String(value)
    }
    default:
      return String(value)
  }
}

/** Opciones de un campo de selección (fijas o tomadas de otros maestros). */
export function optionsOf(field: FieldSpec, lookups: Lookups): [string, string][] {
  if (field.options.length > 0) return field.options
  switch (field.options_from) {
    case 'vehicle_types':
      return lookups.vehicle_types.map((v) => [v, v])
    case 'corridors':
      return lookups.corridors.map(([code, name]) => [code, `${code} · ${name}`])
    case 'customers':
      return lookups.customers.map(([code, name]) => [code, `${code} · ${name}`])
    default:
      return []
  }
}

/** Clave de una fila según los campos clave del maestro. */
export const keyOf = (row: MasterRow, keyFields: readonly string[]): string =>
  keyFields.map((k) => String(row[k])).join('|')

/** Campos que cambiaron entre dos versiones de un registro (para el historial). */
export function changedFields(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
): { name: string; before: unknown; after: unknown }[] {
  const names = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])
  return [...names]
    .filter((n) => JSON.stringify(before?.[n]) !== JSON.stringify(after?.[n]))
    .map((name) => ({ name, before: before?.[name], after: after?.[name] }))
}

/** Texto de ayuda con las columnas de la plantilla CSV de un maestro. */
export const csvColumns = (fields: readonly FieldSpec[]): string =>
  fields.map((f) => (f.required ? f.name : `${f.name} (opcional)`)).join(', ')
