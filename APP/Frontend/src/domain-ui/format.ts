// Formatos exclusivamente de presentación. No contiene reglas de negocio.

export const BOGOTA_TZ = 'America/Bogota'
export const NOT_AVAILABLE = 'No disponible'

const integer = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const twoDecimals = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const money = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
})

/** Un valor ausente (null/undefined/NaN) NUNCA se muestra como 0. */
const missing = (value: number | null | undefined): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value)

export const formatInt = (value: number | null | undefined): string =>
  missing(value) ? NOT_AVAILABLE : integer.format(value)

export const formatDecimal = (value: number | null | undefined, digits: 1 | 2 = 1): string =>
  missing(value) ? NOT_AVAILABLE : (digits === 1 ? oneDecimal : twoDecimals).format(value)

/** Recibe una fracción (0,085) y devuelve "8,5 %". */
export const formatPercent = (fraction: number | null | undefined): string =>
  missing(fraction) ? NOT_AVAILABLE : `${oneDecimal.format(fraction * 100)} %`

/** Recibe un porcentaje ya expresado en 0–100. */
export const formatPercentPoints = (points: number | null | undefined): string =>
  missing(points) ? NOT_AVAILABLE : `${oneDecimal.format(points)} %`

export const formatMoney = (value: number | null | undefined): string =>
  missing(value) ? NOT_AVAILABLE : money.format(value)

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return NOT_AVAILABLE
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return NOT_AVAILABLE
  const text = new Intl.DateTimeFormat('es-CO', {
    timeZone: BOGOTA_TZ,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
  return `${text} (hora de Bogotá)`
}

/** Brecha de flota: negativa = déficit. El texto acompaña al símbolo (no solo color). */
export function describeGap(gap: number): { label: string; kind: 'deficit' | 'surplus' | 'balanced' } {
  if (gap < 0) return { label: `Déficit de ${integer.format(-gap)}`, kind: 'deficit' }
  if (gap > 0) return { label: `Holgura de ${integer.format(gap)}`, kind: 'surplus' }
  return { label: 'Equilibrada', kind: 'balanced' }
}

const VEHICLE_LABELS: Record<string, string> = {
  turbo: 'Turbo',
  sencillo: 'Sencillo',
  doble_troque: 'Doble troque',
  tractomula: 'Tractomula',
  TOTAL: 'Total',
}

export const vehicleLabel = (type: string): string =>
  VEHICLE_LABELS[type] ?? type.replace(/_/g, ' ')

const SOLVER_LABELS: Record<string, string> = {
  optimal: 'Óptima',
  feasible: 'Factible (sin prueba de optimalidad)',
  infeasible: 'Inviable',
  time_limit: 'Límite de tiempo agotado',
  error: 'Error del solver',
}

export const solverStatusLabel = (status: string): string => SOLVER_LABELS[status] ?? status

const SCENARIO_LABELS: Record<string, string> = {
  base: 'Base',
  optimista: 'Optimista',
  pesimista: 'Pesimista',
}

export const scenarioLabel = (name: string): string => SCENARIO_LABELS[name] ?? name
