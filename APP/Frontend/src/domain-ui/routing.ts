// Presentación del módulo de ruteo. Sin reglas de negocio: solo formatos y etiquetas.

import type {
  EventType,
  ProposalStatus,
  RouteStatus,
  RoutingStop,
  RoutingVehicle,
  StopState,
  VehicleStatus,
} from '../api/types'

/** Minutos desde la medianoche a "HH:MM" (redondeado al minuto). */
export function formatClock(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return '—'
  const total = Math.round(minutes)
  const hh = Math.floor(total / 60) % 24
  const mm = ((total % 60) + 60) % 60
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}

/** "HH:MM" a minutos; null si el texto no es una hora válida. */
export function parseClock(text: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim())
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (hours > 23 || minutes > 59) return null
  return hours * 60 + minutes
}

export const formatMinutes = (minutes: number): string =>
  `${Math.round(minutes).toLocaleString('es-CO')} min`

export const VEHICLE_STATUS_LABELS: Record<VehicleStatus, string> = {
  not_started: 'En el CEDI, aún no sale',
  traveling: 'En camino',
  waiting: 'Esperando que abra la ventana',
  serving: 'Entregando',
  returning: 'Regresando al CEDI',
  at_depot: 'En el CEDI (terminó)',
  broken: 'Averiado',
  standby: 'Disponible (sin ruta)',
}

export const vehicleStatusLabel = (status: VehicleStatus): string =>
  VEHICLE_STATUS_LABELS[status] ?? status

export const ROUTE_STATUS_LABELS: Record<RouteStatus, string> = {
  active: 'En operación',
  broken: 'Averiado',
  standby: 'En espera',
}

export const KIND_LABELS = {
  own: 'Propio',
  reserve: 'Reserva',
  third_party: 'Tercero',
} as const

export const STOP_STATE_LABELS: Record<StopState, string> = {
  completed: 'Entregada',
  in_service: 'En servicio',
  pending: 'Pendiente',
  planned: 'Planeada',
}

export const STOP_KIND_LABELS = {
  delivery: 'Entrega',
  transfer: 'Transbordo',
  reload: 'Recarga en CEDI',
} as const

export const EVENT_LABELS: Record<EventType, string> = {
  road_closure: 'Cierre vial',
  urgent_order: 'Pedido urgente',
  window_change: 'Cambio de ventana',
  breakdown: 'Avería',
  delay_risk: 'Riesgo de retraso',
}

export const PROPOSAL_LABELS: Record<ProposalStatus, string> = {
  pending: 'Pendiente de decisión',
  approved: 'Aprobada',
  rejected: 'Rechazada',
  superseded: 'Obsoleta (se recalculó)',
  none_needed: 'Sin cambios necesarios',
}

export const PROPOSAL_TONES: Record<ProposalStatus, 'ok' | 'warn' | 'bad' | 'neutral'> = {
  pending: 'warn',
  approved: 'ok',
  rejected: 'bad',
  superseded: 'neutral',
  none_needed: 'neutral',
}

/** Paleta apta para daltonismo (Okabe-Ito); el vehículo siempre se identifica también por su placa. */
export const VEHICLE_COLORS = [
  '#0072B2',
  '#D55E00',
  '#009E73',
  '#CC79A7',
  '#E69F00',
  '#56B4E9',
  '#6a3d9a',
  '#444444',
] as const

export const colorOfVehicle = (vehicles: readonly RoutingVehicle[], id: string): string => {
  const index = Math.max(
    0,
    vehicles.findIndex((v) => v.id === id),
  )
  return VEHICLE_COLORS[index % VEHICLE_COLORS.length] ?? VEHICLE_COLORS[0]
}

/** Texto de la ventana horaria de una parada ("08:00–12:00") o "—" si no tiene. */
export const windowText = (stop: Pick<RoutingStop, 'window_start_min' | 'window_end_min'>): string =>
  stop.window_start_min === null || stop.window_end_min === null
    ? '—'
    : `${formatClock(stop.window_start_min)}–${formatClock(stop.window_end_min)}`

export const SPEED_OPTIONS = [1, 10, 30, 60, 120] as const

export const INCIDENT_LABELS: Record<string, string> = {
  customer_absent: 'Cliente ausente',
  access_blocked: 'Acceso bloqueado',
  damaged_goods: 'Mercancía dañada',
  vehicle_issue: 'Problema del vehículo',
  other: 'Otra novedad',
}
